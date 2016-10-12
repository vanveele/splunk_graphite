#!/usr/bin/env python

"""Datadog output for Splunk."""


__author__ = 'Robert van Veelen <robert.vanveelen@gmail.com>'
__license__ = 'Apache License, Version 2.0'


import argparse
import ConfigParser
import csv
import gzip
import os
import socket
import requests
import sys
import time
import traceback


# We'll ignore these number-like Splunk fields when forwarding events.
IGNORE_FIELDS = ['linecount', 'timeendpos', 'timestartpos']
DD_API_KEY = ''
DD_API_URL = 'http://localhost:17123/api/v1/series'
DD_API_PARAMS = {
    'api_key': DD_API_KEY
}


def generate_splunk_error(trace):
    """Wrapper for `splunk.Intersplunk.generateErrorResults`.

    Allows us to test this script w/o 'import splunk' errors.
    Ghetto - I know.

    @param trace: Traceback to pass to Splunk's error handler.
    @type trace: str
    """
    import splunk.Intersplunk
    splunk.Intersplunk.generateErrorResults(trace)


def get_config_file():
    """Gets Datadog output config file location.

    @return: Path to Datadog output config file.
    @rtype: str
    """
    config_file = ''
    splunk_home = os.environ.get('SPLUNK_HOME')

    if splunk_home and os.path.exists(splunk_home):
        config_path = os.path.join(
            splunk_home, 'etc', 'apps', 'splunk_datadog', 'local',
            'datadog.conf')
        if os.path.exists(config_path):
            config_file = config_path

    return config_file


# TODO(gba) Refactor this config code, there's too many conditionals here.
def get_datadog_config(config_file, args=None):
    """Extracts Datadog output config settings from file or args.

    @param config_file: Config file from which to attempt to retrieve settings.
    @type config_file: str
    @param args: Configuration settings passed-in as arguments.
    @type args: `argparse.ArgumentParser`

    @return: Dictionary of host, port, namespace, prefix config settings.
    @rtype: dict
    """
    if args:
        datadog_config = {
            'host': args.host,
            'port': args.port,
            'namespace': args.namespace,
            'prefix': args.prefix,
            'namefield': args.namefield,
            'tags': args.tags
        }
    else:
        datadog_config = {
            'host': 'localhost',
            'port': '2003',
            'namespace': 'splunk.search',
            'prefix': '',
            'tags': None
            'namefield': None
        }

    if config_file and os.path.exists(config_file):
        config = ConfigParser.SafeConfigParser(datadog_config)
        config.read(config_file)

        # Cast ConfigParser.items()'s list of tuples into dict:
        datadog_config = dict(
            (x, y) for x, y in config.items('datadog_config'))

    return datadog_config


def extract_results(results_file):
    """Extracts results data from Splunk CSV file.

    @param results_file: Path to GZIP compressed CSV file.
    @type results_file: str

    @return: results from CSV file.
    @rtype: list
    """
    results = []

    if results_file and os.path.exists(results_file):
        results = csv.DictReader(gzip.open(results_file))

    return results


def collect_metrics(results, select_fields=None, namefield=None):
    """Collects metrics from search result fields.

    @param results: Splunk's search results.
    @type results: dict
    @param select_fields: Fields to select from search results.
    @type select_fields: list
    @param namefield: Field with metric name (prefix)
    @type namefield: string

    @return: Collected metrics in 'field value ts' format.
    @rtype: list
    """
    metrics = []

    for result in results:
        nameprefix = None

        if namefield:
            nameprefix = result[namefield]

        for rkey, rval in result.items():
            metric_value = None
            metric_name = None

            # Scalars and floats can both be casted to float without
            # throwing a ValueError.
            try:
                metric_value = float(rval)
            except ValueError:
                pass

            if select_fields and rkey in select_fields:
                metric_name = rkey
            elif (not select_fields and '_' not in rkey[0] and 'date_' not
                    in rkey[0:5] and rkey not in IGNORE_FIELDS):
                metric_name = rkey

            if namefield and nameprefix and metric_name:
                metric_name = '.'.join([nameprefix, metric_name])

            # TODO use datadog API if time is required.
            if '_time' in result:
                result['__ts__'] = result['_time']
            elif '_indextime' in result:
                result['__ts__'] = result['_indextime']
            else:
                result['__ts__'] = time.time()

            # Yes, I mean "metric_value is not None" because '0' & '0.0' are
            # both valid values but eval to False in Python :\.
            if metric_name and metric_value is not None:
                # e.g. "memory 4800.0 12345678"
                metric = ' '.join([
                    metric_name,
                    str(metric_value),
                    # Carbon wants an int:
                    str(int(float(result['__ts__'])))
                ])

                metric = {
                    'metric': metric_name,
                    'points': [[str(int(float(result['__ts__']))), str(metric_value)]],
                    'type': gauge,
                    'host': socket.gethostname(),
                    'tags': ['test']
                }
                metrics.append(metric)

    return metrics


def render_metrics(metrics, namespace, prefix=None):
    """Renders collected metrics into 'prefix.namespace.metric x y' list.

    @param metrics: List of collected metrics.
    @type metrics: list
    @param namespace: Graphite metrics namespace.
    @type namespace: str
    @param prefix: Prefix for metrics namespace (e.g. for hostedgraphite.com).
    @type prefix: str

    @return: List of rendered metris.
    @rtype: list
    """
    full_ns = [namespace]

    if prefix:
        full_ns.insert(0, prefix)

    return ['.'.join(full_ns + [met]) for met in metrics]


def process_results(results, args=None):
    """
    Processes Splunk search results into Datadog output.

    @param results: Splunk search results.
    @type results: dict
    @param args: Config settings passed in as arguments
    @type args: `argparse.ArgumentParser`
    """
    if args:
        config_args = args[0]
        select_fields = args[1]
    else:
        config_args = None
        select_fields = None

    datadog_config = get_datadog_config(get_config_file(), config_args)

    collected_metrics = collect_metrics(
        results=results,
        select_fields=select_fields,
        namefield=datadog_config['namefield']
    )

    rendered_metrics = render_metrics(
        metrics=collected_metrics,
        namespace=datadog_config['namespace'],
        prefix=datadog_config['prefix']
    )

    if not config_args.noop:
        send_metrics(
            metrics=rendered_metrics,
            host=graphite_config['host'],
            port=graphite_config['port']
        )

    output_results = [dict(zip(['metric', 'value', '_time'], m.split()))
        for m in rendered_metrics]

    import splunk.Intersplunk
    splunk.Intersplunk.outputResults(output_results)


def send_metrics(metrics, host, port):
    """Sends metrics to Datadog API.

    @param metrics: List of metrics to send.
    @type metrics: list
    @param host: Destination host for metrics.
    @type host: str
    @param port: Destination port for metrics.
    @type port: int
    """
    if metrics:
        sock = socket.socket()
        sock.settimeout(6)
        sock.connect((host, int(port)))
        sock.sendall('\n'.join(metrics) + '\n')
        sock.shutdown(1)

    if metrics:
        series = json.dumps({
            'series': metrics
        })

        response = requests.put(
            url = DD_API_URL,
            params = DD_API_PARAMS,
            data = series
        )


def alert_command():
    """Invokes Datadog output as a Saved-Search Alert Command."""
    results = extract_results(os.environ.get('SPLUNK_ARG_8'))
    process_results(results)


def search_command(args):
    """
    Invokes Datadog output as a Search Command.

    @param args: Config settings passed in as arguments
    @type args: `argparse.ArgumentParser`
    """
    import splunk.Intersplunk

    # readResults(): Converts an Intersplunk-formatted file object into a
    # dict representation of the contained events.
    results = splunk.Intersplunk.readResults(None, {})

    process_results(results, args)


def main(argz=None):
    """Differentiates alert invocation from search invocation."""

    try:
        if 'SPLUNK_ARG_1' in os.environ:
            alert_command()
        else:
            if not argz:
                # Ignore arg[0], which is the name of this script.
                argz = sys.argv[1:]

            parser = argparse.ArgumentParser()
            parser.add_argument('--host', default='localhost')
            parser.add_argument('--port', default='17123')
            parser.add_argument('--namespace', default='splunk.search')
            parser.add_argument('--prefix', default=None)
            parser.add_argument('--namefield', default=None)
            parser.add_argument('--noop', action='store_true')
            parser.add_help = False
            args = parser.parse_known_args(argz)

            search_command(args)
    except Exception:  # pylint: disable=W0703
        generate_splunk_error(traceback.format_exc())


if __name__ == '__main__':
    sys.exit(main())
