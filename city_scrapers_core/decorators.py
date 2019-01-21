from functools import wraps


def ignore_jscalendar(func):
    """Method decorator to ignore JSCalendar items passed to pipeline by middleware"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        for i in range(2):
            if isinstance(args[i], dict) and "cityscrapers.org/id" in args[i]:
                return args[i]
        return func(*args, **kwargs)

    return wrapper
