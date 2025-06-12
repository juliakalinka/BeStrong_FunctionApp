import logging

def main(blob: bytes, name: str):
    logging.info(f"NotificationFunction triggered by blob: {name}")
