# echo.py: Tracing function calls using Python decorators.
#
# Written by Thomas Guest <tag@wordaligned.org>
# Please see http://wordaligned.org/articles/echo
#
# Place into the public domain.

"""Echo calls made to functions and methods in a module.

"Echoing" a function call means printing out the name of the function
and the values of its arguments before making the call (which is more
commonly referred to as "tracing", but Python already has a trace module).

Example: to echo calls made to functions in "my_module" do:

  import echo
  import my_module
  echo.echo_module(my_module)

Example: to echo calls made to functions in "my_module.my_class" do:

  echo.echo_class(my_module.my_class)

Alternatively, echo.echo can be used to decorate functions. Calls to the
decorated function will be echoed.

Example:
-------
  @echo.echo
  def my_function(args):
      pass


"""

from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import MethodType
    from typing import Any, Callable


def name(item: Callable) -> str:
    """Return an item's name."""
    return item.__name__


def is_classmethod(instancemethod: MethodType, klass: type) -> bool:
    """Determine if an instancemethod is a classmethod."""
    return inspect.ismethod(instancemethod) and instancemethod.__self__ is klass


def is_static_method(method: MethodType, klass: type) -> bool:
    """Returns True if method is an instance method of klass."""
    return next(
        (isinstance(c.__dict__[name(method)], staticmethod) for c in klass.mro() if name(method) in c.__dict__),
        False,
    )


def is_class_private_name(name: str) -> bool:
    """Determine if a name is a class private name."""
    # Exclude system defined names such as __init__, __add__ etc
    return name.startswith("__") and not name.endswith("__")


def method_name(method: MethodType) -> str:
    """Return a method's name.

    This function returns the name the method is accessed by from
    outside the class (i.e. it prefixes "private" methods appropriately).
    """
    mname = name(method)
    if is_class_private_name(mname):
        mname = f"_{name(method.__self__.__class__)}{mname}"
    return mname


def format_arg_value(arg_val: tuple[str, tuple[Any, ...]]) -> str:
    """Return a string representing a (name, value) pair."""
    arg, val = arg_val
    return f"{arg}={val!r}"


def echo(fn: Callable, write: Callable[[str], int | None] = sys.stdout.write) -> Callable:
    """Echo calls to a function.

    Returns a decorated version of the input function which "echoes" calls
    made to it by writing out the function's name and the arguments it was
    called with.
    """
    import functools

    # Unpack function's arg count, arg names, arg defaults
    code = fn.__code__
    argcount = code.co_argcount
    argnames = code.co_varnames[:argcount]
    fn_defaults: tuple[Any] = fn.__defaults__ or ()
    argdefs = dict(list(zip(argnames[-len(fn_defaults) :], fn_defaults)))

    @functools.wraps(fn)
    def wrapped(*v: Any, **k: Any) -> Callable:
        # Collect function arguments by chaining together positional,
        # defaulted, extra positional and keyword arguments.
        positional = list(map(format_arg_value, list(zip(argnames, v))))
        defaulted = [format_arg_value((a, argdefs[a])) for a in argnames[len(v) :] if a not in k]
        nameless = list(map(repr, v[argcount:]))
        keyword = list(map(format_arg_value, list(k.items())))
        args = positional + defaulted + nameless + keyword
        write(f"{name(fn)}({', '.join(args)})\n")
        return fn(*v, **k)

    return wrapped


def echo_instancemethod(klass: type, method: MethodType, write: Callable[[str], int | None] = sys.stdout.write) -> None:
    """Change an instancemethod so that calls to it are echoed.

    Replacing a classmethod is a little more tricky.
    See: http://www.python.org/doc/current/ref/types.html
    """
    mname = method_name(method)

    # Avoid recursion printing method calls
    if mname in {"__str__", "__repr__"}:
        return

    if is_classmethod(method, klass):
        setattr(klass, mname, classmethod(echo(method.__func__, write)))
    else:
        setattr(klass, mname, echo(method, write))


def echo_class(klass: type, write: Callable[[str], int | None] = sys.stdout.write) -> None:
    """Echo calls to class methods and static functions"""
    for _, method in inspect.getmembers(klass, inspect.ismethod):
        # In python 3 only class methods are returned here
        echo_instancemethod(klass, method, write)
    for _, fn in inspect.getmembers(klass, inspect.isfunction):
        if is_static_method(fn, klass):
            setattr(klass, name(fn), staticmethod(echo(fn, write)))
        else:
            # It's not a class or a static method, so it must be an instance method.
            echo_instancemethod(klass, fn, write)


def echo_module(mod: MethodType, write: Callable[[str], int | None] = sys.stdout.write) -> None:
    """Echo calls to functions and methods in a module."""
    for fname, fn in inspect.getmembers(mod, inspect.isfunction):
        setattr(mod, fname, echo(fn, write))
    for _, klass in inspect.getmembers(mod, inspect.isclass):
        echo_class(klass, write)
