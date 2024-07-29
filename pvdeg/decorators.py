"""
Utility Decorators for PVDeg.
Private API, should only be used in PVDeg implemenation files.
"""

def geospatial_result_type(value: bool, shape_names: list[str]) -> None:
    """
    Add an attribute to the functions that can be run with geospatial analysis. 
    Strict typing is not enough for this purpose so we can view this attribute 
    at runtime to create a template for the function. 

    For single numeric results, includes tabular numeric data 
    >>> value = False (0) 

    Example if a function returns a dataframe with 1 row of numerics (not timeseries)
    `pvdeg.standards.standoff` does this.

    For timeseries results
    >>> value = True (1)

    Example, `pvdeg.temperature.temperature`

    For both numeric and timeseries results, we care about the output names of the funtion.
    When a function returns a dataframe, the names will simply be the dataframe column names.
    >>> return df # function returns dataframe 
    >>> df.columns = ["rh", "dry_bulb", "irradiance"] # dataframe column names
    >>> func.shape_names = ["rh", "dry_bulb", "irradiance"] # function attribute names

    When a function returns a numeric, or tuple of numerics, the names will correspond to the meanings of each unpacked variable.
    >>> return (T98, x_eff) # function return tuple of numerics
    >>> func.shape_names = ["T98", "x_eff"] # function attribute names
    
    """
    def decorator(func):
        setattr(func, "numeric_or_timeseries", value)
        setattr(func, "shape_names", shape_names)
        return func
    return decorator