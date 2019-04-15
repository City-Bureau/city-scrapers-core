from functools import wraps


def ignore_processed(func):
    """Method decorator to ignore processed items passed to pipeline by middleware"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        for i in range(2):
            if isinstance(args[i], dict) and ("uid" in args[i] or "_id" in args[i]):
                return args[i]
        return func(*args, **kwargs)

    return wrapper
