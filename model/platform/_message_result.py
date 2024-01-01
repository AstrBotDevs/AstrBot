from dataclasses import dataclass
from typing import Union, Optional

@dataclass
class MessageResult():
    result_message: Union[str, list]
    is_command_call: Optional[bool] = False
    callback: Optional[callable] = None
