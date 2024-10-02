from typing import List
import casadi as cs
import numpy as np

def get_sub_config(id: str, config: dict) -> dict:
    sub_config = {}
    for config_id, config_member in config.items():
        if config_id.find(id) == -1:
            continue
        else:
            sub_config[config_id] = config_member
    return sub_config

def get_dimensions(id: str, config: dict) -> int:
    sub_config = get_sub_config(config, id)
    dims = 0
    for config_member in sub_config.values():
        dims += config_member["dimensions"]
    return dims

def get_all_dimensions(config: dict) -> int:
    dims = 0
    for config_member in config.values():
        dims += config_member["dimensions"]
    return dims

def get_start_or_end_index(id: str, config: dict, is_start: bool) -> int:
    i = 0
    for config_id in config.keys():
        if not is_start:
            i += config[config_id]["dimensions"]
        if config_id == id:
            return i
        elif config_id == list(config.keys())[-1]:
            raise IndexError
        elif is_start:
            i += config[config_id]["dimensions"]

def get_start_index(id: str, config: dict) -> int:
    return get_start_or_end_index(config=config, id=id, is_start=True)

def get_stop_index(id: str, config: dict) -> int:
    return get_start_or_end_index(config=config, id=id, is_start=False)

def get_subvector(id: str, vector, config: dict):
    return vector[get_start_index(id, config) : get_stop_index(id, config)]

def symbolic(id: str, config: dict) -> cs.SX:
    return cs.SX.sym(id, config[id]["dimensions"])

def get_default_vector(id: str, dimensions: int, config: dict, ) -> np.ndarray:
    i = 0
    vector = []
    for config_id in config.keys():
        vector += list(config[config_id][id])
        i += config[config_id]["dimensions"]
        if i > dimensions:
            raise IndexError
        elif i == dimensions:
            return np.array(vector)
    raise IndexError
