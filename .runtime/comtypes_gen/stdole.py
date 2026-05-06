from enum import IntFlag

import comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 as __wrapper_module__
from comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 import (
    OLE_HANDLE, IPictureDisp, OLE_CANCELBOOL, FONTUNDERSCORE,
    FONTSIZE, IFontEventsDisp, Font, typelib_path, FONTSTRIKETHROUGH,
    VgaColor, OLE_YPOS_PIXELS, OLE_XPOS_CONTAINER, Library,
    OLE_OPTEXCLUSIVE, OLE_XSIZE_CONTAINER, OLE_YPOS_HIMETRIC, IFont,
    OLE_XSIZE_PIXELS, Monochrome, Checked, HRESULT, IEnumVARIANT,
    OLE_YSIZE_HIMETRIC, FONTBOLD, Default, Color, GUID,
    OLE_YSIZE_CONTAINER, _lcid, OLE_COLOR, StdPicture, dispid,
    IPicture, Picture, OLE_YSIZE_PIXELS, BSTR, _check_version,
    StdFont, EXCEPINFO, IUnknown, Gray, IFontDisp, COMMETHOD,
    OLE_ENABLEDEFAULTBOOL, Unchecked, DISPPARAMS, FONTITALIC,
    OLE_YPOS_CONTAINER, OLE_XPOS_HIMETRIC, OLE_XSIZE_HIMETRIC,
    DISPMETHOD, IDispatch, CoClass, FONTNAME, VARIANT_BOOL,
    FontEvents, DISPPROPERTY, OLE_XPOS_PIXELS
)


class LoadPictureConstants(IntFlag):
    Default = 0
    Monochrome = 1
    VgaColor = 2
    Color = 4


class OLE_TRISTATE(IntFlag):
    Unchecked = 0
    Checked = 1
    Gray = 2


__all__ = [
    'OLE_HANDLE', 'OLE_COLOR', 'IPictureDisp', 'OLE_CANCELBOOL',
    'StdPicture', 'IPicture', 'Picture', 'FONTUNDERSCORE', 'FONTSIZE',
    'IFontEventsDisp', 'Font', 'OLE_YSIZE_PIXELS', 'typelib_path',
    'FONTSTRIKETHROUGH', 'StdFont', 'VgaColor', 'OLE_YPOS_PIXELS',
    'Gray', 'OLE_XPOS_CONTAINER', 'IFontDisp', 'Library',
    'OLE_ENABLEDEFAULTBOOL', 'Unchecked', 'OLE_OPTEXCLUSIVE',
    'FONTITALIC', 'OLE_XSIZE_CONTAINER', 'OLE_YPOS_CONTAINER',
    'OLE_XPOS_HIMETRIC', 'OLE_XSIZE_HIMETRIC', 'OLE_TRISTATE',
    'OLE_YPOS_HIMETRIC', 'IFont', 'LoadPictureConstants',
    'OLE_XSIZE_PIXELS', 'Monochrome', 'FONTNAME', 'Checked',
    'FontEvents', 'OLE_YSIZE_HIMETRIC', 'FONTBOLD', 'OLE_XPOS_PIXELS',
    'Default', 'Color', 'OLE_YSIZE_CONTAINER'
]

