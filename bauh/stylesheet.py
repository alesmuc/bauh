import glob
import os
import re
import traceback
from typing import Optional, Dict, Tuple, Set

from PyQt5.QtWidgets import QApplication

from bauh.api.constants import STYLES_PATH
from bauh.view.util import resource
from bauh.view.util.translation import I18n

RE_WIDTH_PERCENT = re.compile(r'[\d\\.]+%w')
RE_HEIGHT_PERCENT = re.compile(r'[\d\\.]+%h')
RE_META_I18N_FIELDS = re.compile(r'((name|description)(\[\w+])?)')


class StylesheetMetadata:

    def __init__(self, file_path: str, default: bool, default_name: Optional[str] = None,
                 default_description: Optional[str] = None, version: Optional[str] = None,
                 root_sheet: Optional[str] = None):
        self.names = {}
        self.default_name = default_name
        self.descriptions = {}
        self.default_description = default_description
        self.root_sheet = root_sheet
        self.version = version
        self.hardcoded_stylesheets = False
        self.file_path = file_path
        self.file_dir = '/'.join(file_path.split('/')[0:-1])
        self.default = default
        self.key = self.file_path.split('/')[-1].split('.')[0] if self.default else self.file_path

    def __eq__(self, other) -> bool:
        if isinstance(other, StylesheetMetadata):
            return self.file_path == other.file_path

        return False

    def __hash__(self):
        return self.file_path.__hash__()

    def __repr__(self):
        return self.file_path if self.file_path else ''

    def get_i18n_name(self, i18n: I18n) -> str:
        if self.names:
            name = self.names.get(i18n.current_key, self.names.get(i18n.default_key))

            if name:
                return name

        if self.default_name:
            return self.default_name
        else:
            return self.file_path.split('/')[-1]

    def get_i18n_description(self, i18n: I18n) -> Optional[str]:
        if self.descriptions:
            des = self.descriptions.get(i18n.current_key, self.descriptions.get(i18n.default_key))

            if des:
                return des

        return self.default_description


def read_stylesheet_metada(key: str, file_path: str) -> StylesheetMetadata:
    meta_file = '{}/{}.meta'.format('/'.join(file_path.split('/')[0:-1]), key)
    meta_obj = StylesheetMetadata(file_path=file_path, default_name=key, default=not key.startswith('/'))

    if os.path.exists(meta_file):
        meta_dict = {}
        with open(meta_file) as f:
            for line in f.readlines():
                if line:
                    field_split = line.split('=')

                    if len(field_split) > 1:
                        meta_dict[field_split[0].strip()] = field_split[1].strip()

            if meta_dict:
                for field, val in meta_dict.items():
                    if field == 'version':
                        meta_obj.version = val
                    elif field == 'root_sheet':
                        meta_obj.root_sheet = val
                    elif field == 'name':
                        meta_obj.default_name = val
                    elif field == 'description':
                        meta_obj.default_description = val
                    elif field == 'allow_hardcoded_stylesheets':
                        boolean = val.lower()

                        if boolean == 'true':
                            meta_obj.hardcoded_stylesheets = True
                        elif boolean == 'false':
                            meta_obj.hardcoded_stylesheets = False
                    else:
                        i18n_field = RE_META_I18N_FIELDS.findall(field)

                        if i18n_field:
                            if i18n_field[0][1] == 'name':
                                meta_obj.names[i18n_field[0][2]] = val
                            else:
                                meta_obj.descriptions[i18n_field[0][2]] = val

    return meta_obj


def read_default_stylesheets() -> Dict[str, str]:
    return {f.split('/')[-1].split('.')[0].lower(): f for f in glob.glob(resource.get_path('style/**/*.qss'))}


def read_user_stylesheets() -> Dict[str, str]:
    return {f: f for f in glob.glob('{}/**/*.qss'.format(STYLES_PATH))}


def read_all_stylesheets_metadata() -> Set[StylesheetMetadata]:
    stylesheets = set()

    for key, file_path in read_default_stylesheets().items():
        stylesheets.add(read_stylesheet_metada(key=key, file_path=file_path))

    for key, file_path in read_user_stylesheets():
        stylesheets.add(read_stylesheet_metada(key=key, file_path=file_path))

    return stylesheets


def process_stylesheet(key: str, file_path: str, available_sheets: Optional[Dict[str, str]]) -> Optional[Tuple[str, StylesheetMetadata]]:
    with open(file_path) as f:
        stylesheet_str = f.read()

    if stylesheet_str:
        metadata = read_stylesheet_metada(key=key, file_path=file_path)

        root_sheet = None
        if metadata.root_sheet and metadata.root_sheet in available_sheets:
            root_sheet = process_stylesheet(key=metadata.root_sheet, file_path=available_sheets[metadata.root_sheet],
                                            available_sheets=available_sheets)

        var_map = _read_var_file(file_path)
        var_map['root_img_path'] = resource.get_path('img')
        var_map['style_dir'] = metadata.file_dir

        if var_map:
            for var, value in var_map.items():
                stylesheet_str = stylesheet_str.replace('@' + var, value)

        screen_size = QApplication.primaryScreen().size()
        stylesheet_str = process_width_percent_measures(stylesheet_str, screen_size.width())
        stylesheet_str = process_height_percent_measures(stylesheet_str, screen_size.height())

        return stylesheet_str if not root_sheet else '{}\n{}'.format(root_sheet[0], stylesheet_str), metadata


def process_width_percent_measures(stylesheet, screen_width: int) -> str:
    width_measures = RE_WIDTH_PERCENT.findall(stylesheet)

    final_sheet = stylesheet
    if width_measures:
        for m in width_measures:
            try:
                percent = float(m.split('%')[0])
                final_sheet = final_sheet.replace(m, '{}px'.format(round(screen_width * percent)))
            except ValueError:
                traceback.print_exc()

    return final_sheet


def process_height_percent_measures(stylesheet, screen_height: int) -> str:
    width_measures = RE_HEIGHT_PERCENT.findall(stylesheet)

    final_sheet = stylesheet
    if width_measures:
        for m in width_measures:
            try:
                percent = float(m.split('%')[0])
                final_sheet = final_sheet.replace(m, '{}px'.format(round(screen_height * percent)))
            except ValueError:
                traceback.print_exc()

    return final_sheet


def _read_var_file(stylesheet_file: str) -> dict:
    vars_file = stylesheet_file.replace('.qss', '.vars')
    var_map = {}

    if os.path.isfile(vars_file):
        with open(vars_file) as f:
            for line in f.readlines():
                if line:
                    line_strip = line.strip()
                    if line_strip:
                        var_value = line_strip.split('=')

                        if var_value and len(var_value) == 2:
                            var, value = var_value[0].strip(), var_value[1].strip()

                            if var and value:
                                var_map[var] = value

    return var_map
