# Copyright 2026 Cloudbase Solutions Srl
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

import contextlib
from unittest import mock

import testtools

from mockey.fixture import patch_mock_module
from tests import _original_patch

from .utils import Foo, _ClassReturningThing, _ClassWithInit


class MockIssuesExistTestCase(testtools.TestCase):
    """Verify that the upstream bugs exist when the fixture is NOT active.

    Each test mirrors a counterpart in MockSanityTestCase but asserts the
    *broken* behaviour: wrong-signature calls succeed and non-existent
    attributes do not raise AttributeErrors. If any test here starts failing
    it means the upstream library fixed that issue and the corresponding
    fixture code can be removed.

    For patch-based tests, mock._patch is temporarily restored to the
    original, so that our _patch subclass is not in play.
    """

    @contextlib.contextmanager
    def _restored_patch(self):
        """Temporarily revert mock._patch to the unpatched original."""
        mock._patch = _original_patch  # type: ignore[attr-defined]
        try:
            yield
        finally:
            patch_mock_module()

    def _check_foo_signature_issues(self, foo):
        """Assert that wrong signature calls do NOT raise TypeError.

        Used for patch tests where ``foo`` is a real object with patched
        methods. Attribute existence is enforced by Python itself there,
        not by the fixture, so only signature enforcement is relevant.
        """
        for method_name in ["bar", "classic_bar", "static_bar"]:
            mock_method = getattr(foo, method_name)

            # TypeError is NOT raised if the method signature is not respected.
            mock_method()
            mock_method(mock.sentinel.a)
            mock_method(a=mock.sentinel.a)
            mock_method(
                mock.sentinel.a,
                mock.sentinel.b,
                mock.sentinel.c,
                e=mock.sentinel.e,
            )

    def _check_foo_issues(self, foo):
        """Full check for mock objects: signature + attribute-existence issues."""
        self._check_foo_signature_issues(foo)

        # Without the fixture, this will NOT raise AttributeError.
        lish = foo.lish
        self.assertIsNotNone(lish)

    def _check_mock_issues_without_fixture(self, mock_cls):
        for spec in [Foo, Foo()]:
            # mock.Mock / mock.MagicMock do not have an autospec argument
            # without the fixture. Keeping it here though, as a sanity check,
            # if they will ever have it.
            foo = mock_cls(autospec=spec)
            self._check_foo_issues(foo)
            self._check_foo_issues(foo())

    def test_mock_issues(self):
        self._check_mock_issues_without_fixture(mock.Mock)

    def test_magic_mock_issues(self):
        self._check_mock_issues_without_fixture(mock.MagicMock)

    def test_patch_class(self):
        with (
            self._restored_patch(),
            mock.patch.object(Foo, "bar"),
            mock.patch.object(Foo, "classic_bar"),
            mock.patch.object(Foo, "static_bar"),
        ):
            foo = Foo()
            self._check_foo_signature_issues(foo)

    def test_patch_multiple(self):
        with (
            self._restored_patch(),
            mock.patch.multiple(
                Foo,
                bar=mock.DEFAULT,
                classic_bar=mock.DEFAULT,
                static_bar=mock.DEFAULT,
            ),
        ):
            foo = Foo()
            self._check_foo_signature_issues(foo)

    def test_patch_instance(self):
        foo = Foo()
        with (
            self._restored_patch(),
            mock.patch.object(foo, "bar"),
            mock.patch.object(foo, "classic_bar"),
            mock.patch.object(foo, "static_bar"),
        ):
            self._check_foo_signature_issues(foo)

    def test_return_value_not_autospecced(self):
        # Even with a proper autospec, the return value of a mocked method is
        # not autospecced per type hints, so attribute access and signatures
        # are not enforced on it.
        m = mock.create_autospec(_ClassReturningThing)
        foo = m().get_the_thing()
        self._check_foo_issues(foo)

    def test_return_type_none_not_enforced(self):
        # Even with a proper autospec, -> None return-type hints are NOT
        # enforced; the method returns a Mock instead of None.
        m = mock.create_autospec(_ClassReturningThing)
        result = m().get_none()
        self.assertIsNotNone(result)

    def test_patch_return_value_not_autospecced(self):
        # Even with explicit autospec=True on a patch, the return value is not
        # autospecced per the method's return-type hint.
        thing_returner = _ClassReturningThing()
        with (
            self._restored_patch(),
            mock.patch.object(thing_returner, "get_the_thing", autospec=True),
        ):
            foo = thing_returner.get_the_thing()
            self._check_foo_issues(foo)

    def test_patch_already_mocked_target(self):
        with self._restored_patch(), mock.patch.object(Foo, "bar"):
            # Patching an already patched object should raise an exception,
            # but it doesn't.
            patcher = mock.patch.object(Foo, "bar")
            patcher.start()
            patcher.stop()

            foo = Foo()
            patcher = mock.patch.object(foo, "bar")
            patcher.start()
            patcher.stop()

    def test_constructor_autospec_not_enforced(self):
        # Without the fixture, constructor signature is NOT enforced.
        # mock.Mock / mock.MagicMock do not have an autospec argument
        # without the fixture. Keeping it here though, as a sanity check,
        # if they will ever have it.
        m = mock.Mock(autospec=_ClassWithInit)

        # too many args.
        m(1, 2, 3)

        # missing required arg.
        m(1)

        # unknown kwargs.
        m(x=1, y=2, z=99)
