import time
import functools
from rich.console import Console

console = Console()

def retry_interaction(max_retries=3, delay=2, exceptions=(Exception,)):
    """
    Decorator to retry a function call upon failure.
    
    Args:
        max_retries (int): Number of times to retry.
        delay (int): Seconds to wait between retries.
        exceptions (tuple): Exceptions to catch and retry on.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        console.log(f"[yellow]Action failed: {e}. Retrying ({attempt+1}/{max_retries}) in {delay}s...[/yellow]")
                        time.sleep(delay)
                    else:
                        console.log(f"[red]Action failed after {max_retries} retries.[/red]")
            raise last_exception
        return wrapper
    return decorator
