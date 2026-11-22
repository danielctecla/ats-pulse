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
    notifier = SesNotifier(boto3.client("sesv2"), os.environ["NOTIFICATION_EMAIL"])
    return pipeline.run(load_sources(), store, notifier)
