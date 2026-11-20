select processor_id, name as processor_name, pic as processor_pic
from {{ source('raw', 'hp_processors') }}
