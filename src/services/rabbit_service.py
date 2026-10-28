import os

import pika

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
QUEUE_NAME = "events.incoming"


def publish_event_id(event_id: str) -> None:
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=event_id,
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
        )
    finally:
        connection.close()