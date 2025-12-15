from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union, Tuple

# ---------- existing ----------
class DeviceInfo(BaseModel):  # keep
    id: str
    kind: str
    status: str = "disconnected"  # connected | disconnected | error
    locked_by: Optional[str] = None
    state: Dict[str, Any] = Field(default_factory=dict)

class PatchRequest(BaseModel):
    properties: Dict[str, Any]

class CommandRequest(BaseModel):
    name: str
    args: Dict[str, Any] = {}

class ApplyPropertiesRequest(BaseModel):
    """Request to apply properties from file or inline dict."""
    file_path: Optional[str] = None
    properties: Optional[Dict[str, Dict[str, Any]]] = None

# ---------- NEW: richer /spec models ----------
class ArgSpec(BaseModel):
    name: Optional[str] = None
    type: str
    doc: Optional[str] = None
    required: bool = True
    default: Optional[Any] = None
    choices: Optional[List[str]] = None # for literal types

class CommandSpec(BaseModel):
    name: str
    doc: Optional[str] = None
    args: List[ArgSpec] = Field(default_factory=list)
    events: Optional[Dict[str,str]]

class FieldSpec(BaseModel):
    """Sub-field spec for composite properties (e.g., PID.kp, PID.ki)."""
    doc: Optional[str] = None
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[Union[str, float, int]]] = None

class PropertySpec(BaseModel):
    """Describes a property (read-only or read-write)."""
    name: str
    doc: Optional[str] = None          # <-- your doc field
    read_only: bool = False
    unit: Optional[str] = None
    type: str = "object"  # str, int, float, bool, object
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[List[Union[str, float, int]]] = None  # enums
    fields: Optional[Dict[str, FieldSpec]] = None           # composite sub-fields
    default: Optional[Any] = None
    step: Optional[float] = None       # UI hint for sliders/spinboxes

class DataSourceSpec(BaseModel):
    """Describes a data source (possibly with plot)"""
    name: str
    doc: Optional[str] = None
    has_plot: bool = False

class DeviceSpec(BaseModel):
    """Full capability sheet for one device instance."""
    id: str
    kind: str                             # keep: canonical device type (e.g., 'kcube_piezo')
    driver: Optional[str] = None          # e.g., 'ThorlabsKCubePiezo'
    driver_version: Optional[str] = None
    doc: Optional[str] = None               # human-friendly description
    properties: List[PropertySpec]
    commands: List[CommandSpec]
    data_sources: List[DataSourceSpec]
