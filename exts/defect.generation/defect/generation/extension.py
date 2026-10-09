# SPDX-FileCopyrightText: Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import omni.ext
from omni.kit.menu.utils import MenuItemDescription, add_menu_items, refresh_menu_items, remove_menu_items
from defect.generation.ui.main_window import MainWindow

class DefectsGenerator(omni.ext.IExt):
    WINDOW_NAME = "Defects Sample Extension"
    MENU_PATH = f"Window/{WINDOW_NAME}"

    def __init__(self) -> None:
        super().__init__()
        self._window = None
        self._menu = []

    def on_startup(self, ext_id):
        self._menu = [
            MenuItemDescription(
                name=self.WINDOW_NAME,
                ticked_fn=self._is_window_visible,
                onclick_fn=lambda: self.show_window(None, not self._is_window_visible()),
            )
        ]
        add_menu_items(self._menu, "Window")
        self.show_window(None, True)
    
    def on_shutdown(self):
        if self._menu:
            remove_menu_items(self._menu, "Window")
            self._menu = []
        if self._window:
            self._window.set_visibility_changed_fn(None)
            self._window.destroy()
            self._window = None

    def _is_window_visible(self):
        return self._window is not None and self._window.visible

    def _set_menu(self, value):
        refresh_menu_items("Window")

    def _visibility_changed_fn(self, visible):
        self._set_menu(visible)

    def show_window(self, menu, value):
        if value:
            if self._window is None:
                self._window = MainWindow(DefectsGenerator.WINDOW_NAME, width=450, height=700)
                self._window.set_visibility_changed_fn(self._visibility_changed_fn)
            self._window.visible = True
        elif self._window:
            self._window.visible = False
        self._set_menu(value)
