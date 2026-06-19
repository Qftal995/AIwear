import json
import os
import threading
import time
import uuid
from typing import Callable

import pika
from pika.exchange_type import ExchangeType

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

EXCHANGE = "aiwear.exchange"
IMAGE_TASK_QUEUE = "aiwear.image.tasks"
IMAGE_RESULT_QUEUE = "aiwear.image.results"


def _build_connection():
    creds = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=creds,
        heartbeat=600,
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(params)


_result_store: dict = {}
_result_lock = threading.Lock()


class TaskPublisher:
    """将图片任务发布到 RabbitMQ"""
    def __init__(self):
        self._connection = None
        self._channel = None

    def _ensure_channel(self):
        if self._connection is None or self._connection.is_closed:
            self._connection = _build_connection()
            self._channel = self._connection.channel()
            self._channel.exchange_declare(exchange=EXCHANGE, exchange_type=ExchangeType.direct, durable=True)
            self._channel.queue_declare(queue=IMAGE_TASK_QUEUE, durable=True)
            self._channel.queue_bind(exchange=EXCHANGE, queue=IMAGE_TASK_QUEUE, routing_key="image.task")

    def publish(self, task_type: str, payload: dict) -> str:
        task_id = uuid.uuid4().hex[:12]
        self._ensure_channel()
        body = json.dumps({
            "task_id": task_id,
            "type": task_type,
            "payload": payload,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        self._channel.basic_publish(
            exchange=EXCHANGE,
            routing_key="image.task",
            body=body.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                message_id=task_id,
            ),
        )
        with _result_lock:
            _result_store[task_id] = {"status": "queued", "timestamp": time.time()}
        return task_id

    def close(self):
        if self._channel:
            self._channel.close()
        if self._connection:
            self._connection.close()


class TaskConsumer:
    """消费图片任务，执行后写回结果"""
    def __init__(self, handlers: dict[str, Callable]):
        self.handlers = handlers
        self._connection = None
        self._channel = None

    def _ensure_channel(self):
        if self._connection is None or self._connection.is_closed:
            self._connection = _build_connection()
            self._channel = self._connection.channel()
            self._channel.exchange_declare(exchange=EXCHANGE, exchange_type=ExchangeType.direct, durable=True)
            self._channel.queue_declare(queue=IMAGE_TASK_QUEUE, durable=True)
            self._channel.queue_bind(exchange=EXCHANGE, queue=IMAGE_TASK_QUEUE, routing_key="image.task")
            self._channel.basic_qos(prefetch_count=1)

    def _on_message(self, ch, method, properties, body):
        try:
            task = json.loads(body.decode("utf-8"))
            task_id = task["task_id"]
            task_type = task["type"]
            payload = task.get("payload", {})

            with _result_lock:
                _result_store[task_id] = {"status": "processing", "started_at": time.time()}

            handler = self.handlers.get(task_type)
            if not handler:
                result = {"success": False, "error": f"unknown task type: {task_type}"}
            else:
                result = handler(payload)

            with _result_lock:
                _result_store[task_id] = {
                    "status": "done",
                    "result": result,
                    "finished_at": time.time(),
                }
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            task_id = json.loads(body.decode("utf-8")).get("task_id", "unknown")
            with _result_lock:
                _result_store[task_id] = {"status": "failed", "error": str(e), "finished_at": time.time()}
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start(self):
        self._ensure_channel()
        self._channel.basic_consume(queue=IMAGE_TASK_QUEUE, on_message_callback=self._on_message)
        print(f"[MQ] Worker started, listening on {IMAGE_TASK_QUEUE}")
        self._channel.start_consuming()

    def stop(self):
        if self._channel:
            self._channel.stop_consuming()
        if self._connection:
            self._connection.close()


def get_task_status(task_id: str) -> dict:
    with _result_lock:
        return dict(_result_store.get(task_id, {"status": "not_found"}))


_task_publisher: TaskPublisher = None
_publisher_lock = threading.Lock()


def get_publisher() -> TaskPublisher:
    global _task_publisher
    with _publisher_lock:
        if _task_publisher is None:
            _task_publisher = TaskPublisher()
        return _task_publisher
