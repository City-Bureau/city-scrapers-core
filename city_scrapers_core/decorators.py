from functools import wraps


def ignore_processed(func):
    """Method decorator to ignore processed items passed to pipeline by middleware.

    This should be used on the ``process_item`` method of any additional custom
    pipelines used to handle :class:`Meeting` objects to make sure that ``dict`` items
    passed by :class:`DiffPipeline` don't cause issues.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        for i in range(2):
            if isinstance(args[i], dict) and "_id" in args[i]:
                return args[i]
        return func(*args, **kwargs)

    return wrapper
