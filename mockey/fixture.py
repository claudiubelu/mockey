# Copyright 2017 Cloudbase Solutions Srl
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Based on: https://github.com/openstack/oslotest/blob/0b348bccd3639b6d2a8acd19e62b1dd19ad903d6/oslotest/mock_fixture.py

from __future__ import annotations

import functools
import typing
from typing import TYPE_CHECKING, Any, TypeVar
from unittest import mock

import fixtures

_T = TypeVar("_T")


def _lazy_autospec_method(
    mocked_method: Any,
    original_method: Any,
    eat_self: bool,
) -> None:
    if mocked_method._mock_check_sig.__dict__.get("autospeced"):
        return

    _lazy_autospec: Any = mock.create_autospec(original_method)
    if eat_self:
        # consume self argument.
        _lazy_autospec = functools.partial(_lazy_autospec, None)

    def _autospeced(*args: Any, **kwargs: Any) -> None:
        _lazy_autospec(*args, **kwargs)

    # _mock_check_sig is called by the mock's __call__ method,
    # which means that if a method is not called, _autospeced is not
    # called.
    _autospeced.__dict__["autospeced"] = True
    mocked_method._mock_check_sig = _autospeced

    # If the method declares a concrete return type, autospec the return value,
    # so that attribute access and method signatures are enforced on it too.
    try:
        hints = typing.get_type_hints(original_method)
    except Exception:
        hints = {}

    return_type = hints.get("return")

    if return_type is type(None):
        mocked_method.return_value = None
    elif isinstance(return_type, type):
        rv: Any = _AutospecMagicMock()
        rv.__dict__["_autospec"] = return_type
        mocked_method.return_value = rv


class _AutospecMockMixin:
    """Mock object that lazily autospecs the given spec's methods."""

    # These are defined by mock.Mock but we need to declare them for typing.
    return_value: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        autospec = kwargs.get("autospec")
        self.__dict__["_autospec"] = autospec
        _mock_methods = self.__dict__["_mock_methods"]
        if _mock_methods:
            # allow setting _mock_check_sig when spec_set is given
            _mock_methods.append("_mock_check_sig")

        # callable mocks with autospecs (e.g.: the given autospec is a class)
        # should have their return values autospecced as well.
        if autospec:
            self.return_value.__dict__["_autospec"] = autospec

        # Enforce the constructor signature when the mock itself is called
        # (e.g.: MyClass(wrong_args) should raise TypeError).
        if autospec and isinstance(autospec, type):
            _lazy_autospec_method(self, autospec.__init__, eat_self=True)

    def __getattr__(self, name: str) -> Any:
        attr = super().__getattr__(name)  # type: ignore[misc]

        original_spec = self.__dict__["_autospec"]
        if not original_spec:
            return attr

        if not hasattr(original_spec, name):
            raise AttributeError(name)

        # lazily autospec callable attributes.
        original_attr = getattr(original_spec, name)
        if callable(original_attr):
            # NOTE: _must_skip is a private function in the mock module
            eat_self = mock._must_skip(  # type: ignore[attr-defined]
                original_spec, name, isinstance(original_spec, type)
            )

            _lazy_autospec_method(attr, original_attr, eat_self)

        return attr


class _AutospecMock(_AutospecMockMixin, mock.Mock):
    pass


class _AutospecMagicMock(_AutospecMockMixin, mock.MagicMock):
    pass


class MockAutospecFixture(fixtures.Fixture):
    """A fixture that adds autospec behaviour to mock.Mock and mock.MagicMock.

    The standard mock library has long-standing issues that allow mocked
    methods to be called with wrong signatures without raising an error,
    hiding real bugs.

    This fixture replaces ``unittest.mock.Mock`` and
    ``unittest.mock.MagicMock`` with subclasses that lazily enforce the
    correct call signature whenever the ``autospec`` argument is used.

    Issues addressed:

    * https://github.com/testing-cabal/mock/issues/393
      - mock only accepts a spec / spec_set, and only checks if an attribute
        exists on the spec object; it does not verify that the attribute is
        callable or that its call signature is respected.
    """

    def setUp(self) -> None:
        super().setUp()
        self.useFixture(fixtures.MonkeyPatch("unittest.mock.Mock", _AutospecMock))
        self.useFixture(fixtures.MonkeyPatch("unittest.mock.MagicMock", _AutospecMagicMock))


if TYPE_CHECKING:
    Base = mock._patch
else:
    # As of Python 3.13, mock._patch is not subscriptable at runtime.
    class Base(mock._patch):
        def __class_getitem__(cls, _: Any) -> type:
            return cls


class _patch(Base[_T]):
    """``mock._patch`` subclass with correct autospec handling.

    ``mock.patch`` does not honour the ``autospec`` parameter properly: the
    ``self`` argument is not consumed, so signature assertions fail on
    instance methods. This subclass corrects that behaviour.

    Reference: https://github.com/testing-cabal/mock/issues/396

    Apply globally with :func:`patch_mock_module`.
    """

    def __enter__(self) -> _T:
        # NOTE(claudiub): we're doing the autospec checks here so unit tests
        # have a chance to set up mocks in advance (e.g.: mocking platform
        # specific libraries, which would cause the patch to fail otherwise).

        # By default, autospec is None. We will consider it as True.
        autospec = True if self.autospec is None else self.autospec

        # in some cases, autospec cannot be set to True.
        skip_autospec = (getattr(self, attr) for attr in ["new_callable", "create", "spec"])
        # NOTE(claudiub): The "new" argument is always mock.DEFAULT, unless
        # explicitly set otherwise.
        if self.new is not mock.DEFAULT or any(skip_autospec):
            # cannot autospec if new, new_callable, or create arguments given.
            autospec = False
        elif self.attribute:
            target = getattr(self.getter(), self.attribute, None)
            if isinstance(target, mock.Mock):
                # Don't autospec already-mocked targets; it causes problems
                # with tests that patch mocked methods.
                autospec = False

        # NOTE(claudiub): reset the self.autospec property, so we can handle
        # the autospec scenario ourselves.
        self.autospec = None

        if autospec:
            target = self.getter()
            original_attr = getattr(target, self.attribute)
            # NOTE: _must_skip is a private function in the mock module
            eat_self = mock._must_skip(  # type: ignore[attr-defined]
                target, self.attribute, isinstance(target, type)
            )

            new = super().__enter__()

            # NOTE(claudiub): mock.patch.multiple will cause new to be a
            # dict.
            mocked_method = new[self.attribute] if isinstance(new, dict) else new
            _lazy_autospec_method(mocked_method, original_attr, eat_self)
            return new
        else:
            return super().__enter__()


def patch_mock_module() -> None:
    """Replace ``mock._patch`` with a version that enforces autospec.

    Must be called before any test modules are imported, because
    ``mock.patch`` decorators capture ``mock._patch`` at import time.
    Call this once at test-suite startup, e.g. from ``tests/__init__.py``::

        # tests/__init__.py
        from mockey.fixture import patch_mock_module

        patch_mock_module()
    """
    mock._patch = _patch  # type: ignore[misc]
