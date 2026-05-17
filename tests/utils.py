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


class Foo:
    def bar(self, a, b, c, d=None):
        pass

    @classmethod
    def classic_bar(cls, a, b, c, d=None):
        pass

    @staticmethod
    def static_bar(a, b, c, d=None):
        pass


class _ClassWithInit:
    def __init__(self, x: int, y: int) -> None:
        pass

    def method(self, z: str) -> None:
        pass


class _ClassReturningThing:
    def get_the_thing(self) -> Foo:
        return Foo()

    def get_none(self) -> None:
        pass
