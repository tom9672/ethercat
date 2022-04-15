import ctypes
class OutputPdo(ctypes.Structure):
    _pack_ = 1
    _fields_ =[
        ('Control_Word',ctypes.c_uint16),
        ('Mode_Operation',ctypes.c_int8),
        ('Target_Position',ctypes.c_int32),
        ('target_speed_pp', ctypes.c_uint32),
        ('target_speed_pv', ctypes.c_int32)
    ]

class InputPdo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('status_word',ctypes.c_uint16),
        ('actual_position',ctypes.c_int32),
        ('actual_speed',ctypes.c_int32),
    ]