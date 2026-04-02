from dataclasses import dataclass, field
from typing import List, Optional, Union

@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

@dataclass
class TextRun:
    text: str
    font_family: str
    font_size_pt: float
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None
    char_spacing: Optional[float] = None
    baseline_shift: Optional[float] = None
    language: Optional[str] = None

@dataclass
class Paragraph:
    runs: List[TextRun] = field(default_factory=list)
    alignment: Optional[str] = None
    space_before: Optional[float] = None
    space_after: Optional[float] = None

@dataclass
class TextBox:
    bbox: Rect
    paragraphs: List[Paragraph]
    writing_mode: Optional[str] = None
    alignment: Optional[str] = None
    line_spacing: Optional[float] = None
    fill_color: Optional[str] = None
    stroke_color: Optional[str] = None
    rotation: float = 0.0
    z_index: int = 0
    is_ocr: bool = False

@dataclass
class ImageElement:
    bbox: Rect
    image_ref: str
    mime_type: Optional[str]
    pixel_width: int
    pixel_height: int
    transform: Optional[list] = None
    alpha: bool = False
    rotation: float = 0.0
    z_index: int = 0

PageElement = Union[TextBox, ImageElement]

@dataclass
class PageModel:
    index: int
    width_pt: float
    height_pt: float
    elements: List[PageElement] = field(default_factory=list)

@dataclass
class DocumentModel:
    source_path: str
    pages: List[PageModel]
    metadata: dict
