"""Lambda entry point, invoked by EventBridge Scheduler."""

import logging
import os

import boto3

from . import pipeline
from .config import load_sources
from .notify import SesNotifier
from .store import Store

logging.getLogger("ats_pulse").setLevel(logging.INFO)


def lambda_handler(event, context):
    store = Store(boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"]))
    sources = load_sources()
    logos = {s.company: s.logo for s in sources if s.logo}
    notifier = SesNotifier(boto3.client("sesv2"), os.environ["NOTIFICATION_EMAIL"], logos)
    return pipeline.run(sources, store, notifier)
