"""Lambda entry point, invoked by EventBridge Scheduler."""

import logging
import os

import boto3

from . import pipeline
from .config import load_sources
from .notify import LogNotifier
from .store import Store

logging.getLogger("ats_pulse").setLevel(logging.INFO)


def lambda_handler(event, context):
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return pipeline.run(load_sources(), Store(table), LogNotifier())
