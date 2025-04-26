import logging
import os
from datetime import datetime

def setup_logger(name: str) -> logging.Logger:
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create file handler
    current_time = datetime.now().strftime('%Y-%m-%d')
    file_handler = logging.FileHandler(f'logs/news_sharer_{current_time}.log')
    file_handler.setLevel(logging.DEBUG)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatters and add it to the handlers
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)

    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger 