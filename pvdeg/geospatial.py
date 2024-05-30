"""
Collection of classes and functions for geospatial analysis.
"""

from . import standards
from . import humidity
from . import letid

import xarray as xr
import dask.array as da
import pandas as pd
import numpy as np
from dask.distributed import Client, LocalCluster

import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import cartopy.feature as cfeature

from shapely import LineString, MultiLineString



def start_dask(hpc=None):
    """
    Starts a dask cluster for parallel processing.

    Parameters
    ----------
    hpc : dict
        Dictionary containing dask hpc settings (see examples below).

    Examples
    --------
    Local cluster:

    .. code-block:: python

        hpc = {'manager': 'local',
               'n_workers': 1,
               'threads_per_worker': 8,
               'memory_limit': '10GB'}

    SLURM cluster:

    .. code-block:: python

        kestrel = {
            'manager': 'slurm',
            'n_jobs': 1,  # Max number of nodes used for parallel processing
            'cores': 104,
            'memory': '256GB',
            'account': 'pvsoiling',
            'walltime': '4:00:00',
            'processes': 52,
            'local_directory': '/tmp/scratch',
            'job_extra_directives': ['-o ./logs/slurm-%j.out'],
            'death_timeout': 600,}

    Returns
    -------
    client : dask.distributed.Client
        Dask client object.
    """
    if hpc is None:
        cluster = LocalCluster()
    else:
        manager = hpc.pop("manager")

        if manager == "local":
            cluster = LocalCluster(**hpc)
        elif manager == "slurm":
            from dask_jobqueue import SLURMCluster

            n_jobs = hpc.pop("n_jobs")
            cluster = SLURMCluster(**hpc)
            cluster.scale(jobs=n_jobs)

    client = Client(cluster)
    print("Dashboard:", client.dashboard_link)
    client.wait_for_workers(n_workers=1)

    return client


def calc_gid(ds_gid, meta_gid, func, **kwargs):
    """
    Calculates a single gid for a given function.

    Parameters
    ----------
    ds_gid : xarray.Dataset
        Dataset containing weather data for a single gid.
    meta_gid : dict
        Dictionary containing meta data for a single gid.
    func : function
        Function to apply to weather data.
    kwargs : dict
        Keyword arguments to pass to func.

    Returns
    -------
    ds_res : xarray.Dataset
        Dataset with results for a single gid.
    """

    df_weather = ds_gid.to_dataframe()
    df_res = func(weather_df=df_weather, meta=meta_gid, **kwargs)
    ds_res = xr.Dataset.from_dataframe(df_res)

    if not df_res.index.name:
        ds_res = ds_res.isel(index=0, drop=True)

    return ds_res


def calc_block(weather_ds_block, future_meta_df, func, func_kwargs):
    """
    Calculates a block of gids for a given function.

    Parameters
    ----------
    weather_ds_block : xarray.Dataset
        Dataset containing weather data for a block of gids.
    future_meta_df : pandas.DataFrame
        DataFrame containing meta data for a block of gids.
    func : function
        Function to apply to weather data.
    func_kwargs : dict
        Keyword arguments to pass to func.

    Returns
    -------
    ds_res : xarray.Dataset
        Dataset with results for a block of gids.
    """

    res = weather_ds_block.groupby("gid", squeeze=False).map(
        lambda ds_gid: calc_gid(
            ds_gid=ds_gid.squeeze(),
            meta_gid=future_meta_df.loc[ds_gid["gid"].values[0]].to_dict(),
            func=func,
            **func_kwargs,
        )
    )
    return res


def analysis(weather_ds, meta_df, func, template=None, **func_kwargs):
    """
    Applies a function to each gid of a weather dataset.

    Parameters
    ----------
    weather_ds : xarray.Dataset
        Dataset containing weather data for a block of gids.
    meta_df : pandas.DataFrame
        DataFrame containing meta data for a block of gids.
    func : function
        Function to apply to weather data.
    template : xarray.Dataset
        Template for output data.
    func_kwargs : dict
        Keyword arguments to pass to func.

    Returns
    -------
    ds_res : xarray.Dataset
        Dataset with results for a block of gids.
    """

    if template is None:
        param = template_parameters(func)
        template = output_template(weather_ds, **param)

    # future_meta_df = client.scatter(meta_df)
    kwargs = {"func": func, "future_meta_df": meta_df, "func_kwargs": func_kwargs}

    stacked = weather_ds.map_blocks(
        calc_block, kwargs=kwargs, template=template
    ).compute()

    # lats = stacked.latitude.values.flatten()
    # lons = stacked.longitude.values.flatten()
    stacked = stacked.drop(["gid"])
    # stacked = stacked.drop_vars(['latitude', 'longitude'])
    # stacked.coords["gid"] = pd.MultiIndex.from_arrays(
    #     [meta_df["latitude"], meta_df["longitude"]], names=["latitude", "longitude"]
    # )
    mindex_obj = pd.MultiIndex.from_arrays(
        [meta_df["latitude"], meta_df["longitude"]], names=["latitude", "longitude"]
    )
    mindex_coords = xr.Coordinates.from_pandas_multiindex(mindex_obj, "gid")
    stacked = stacked.assign_coords(mindex_coords)

    stacked = stacked.drop_duplicates("gid")
    res = stacked.unstack("gid")  # , sparse=True
    return res


def output_template(
    ds_gids, shapes, attrs=dict(), global_attrs=dict(), add_dims=dict()
):
    """
    Generates a xarray template for output data. Output variables and
    associated dimensions need to be specified via the shapes dictionary.
    The dimension length are derived from the input data. Additonal output
    dimensions can be defined with the add_dims argument.

    Parameters
    ----------
    ds_gids : xarray.Dataset
        Dataset containing the gids and their associated dimensions.
    shapes : dict
        Dictionary of variable names and their associated dimensions.
    attr : dict
        Dictionary of attributes for each variable (e.g. units).
    add_dims : dict
        Dictionary of dimensions to add to the output template.

    Returns
    -------
    output_template : xarray.Dataset
        Template for output data.
    """
    dims = set([d for dim in shapes.values() for d in dim])
    dims_size = dict(ds_gids.sizes) | add_dims

    output_template = xr.Dataset(
        data_vars={
            var: (dim, da.empty([dims_size[d] for d in dim]), attrs.get(var))
            for var, dim in shapes.items()
        },
        coords={dim: ds_gids[dim] for dim in dims},
        attrs=global_attrs,
    ).chunk({dim: ds_gids.chunks[dim] for dim in dims})

    return output_template


def template_parameters(func):
    """
    Output parameters for xarray template.

    Returns
    -------
    shapes : dict
        Dictionary of variable names and their associated dimensions.
    attrs : dict
        Dictionary of attributes for each variable (e.g. units).
    global_attrs: dict
        Dictionary of global attributes for the output template.
    add_dims : dict
        Dictionary of dimensions to add to the output template.
    """

    if func == standards.standoff:
        shapes = {
            "x": ("gid",),
            "T98_inf": ("gid",),
            "T98_0": ("gid",),
        }

        attrs = {
            "x": {"long_name": "Standoff distance", "units": "cm"},
            "T98_0": {
                "long_name": "98th percential temperature of a theoretical module with no standoff",
                "units": "Celsius",
            },
            "T98_inf": {
                "long_name": "98th percential temperature of a theoretical rack mounted module",
                "units": "Celsius",
            },
        }

        global_attrs = {
            "long_name": "Standoff dataset",
        }

        add_dims = {}

    elif func == humidity.module:
        shapes = {
            "RH_surface_outside": ("gid", "time"),
            "RH_front_encap": ("gid", "time"),
            "RH_back_encap": ("gid", "time"),
            "RH_backsheet": ("gid", "time"),
        }

        attrs = {}

        global_attrs = {}

        add_dims = {}

    elif func == letid.calc_letid_outdoors:
        shapes = {
            "Temperature": ("gid", "time"),
            "Injection": ("gid", "time"),
            "NA": ("gid", "time"),
            "NB": ("gid", "time"),
            "NC": ("gid", "time"),
            "tau": ("gid", "time"),
            "Jsc": ("gid", "time"),
            "Voc": ("gid", "time"),
            "Isc": ("gid", "time"),
            "FF": ("gid", "time"),
            "Pmp": ("gid", "time"),
            "Pmp_norm": ("gid", "time"),
        }

        attrs = {}

        global_attrs = {}

        add_dims = {}

    else:
        raise ValueError(f"No preset output template for function {func}.")

    parameters = {
        "shapes": shapes,
        "attrs": attrs,
        "global_attrs": global_attrs,
        "add_dims": add_dims,
    }

    return parameters


def plot_USA(
    xr_res, cmap="viridis", vmin=None, vmax=None, title=None, cb_title=None, fp=None
):
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.LambertConformal(), frameon=False)
    ax.patch.set_visible(False)
    ax.set_extent([-120, -74, 22, 50], ccrs.Geodetic())

    shapename = "admin_1_states_provinces_lakes"
    states_shp = shpreader.natural_earth(
        resolution="110m", category="cultural", name=shapename
    )
    ax.add_geometries(
        shpreader.Reader(states_shp).geometries(),
        ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="gray",
    )

    cm = xr_res.plot(
        transform=ccrs.PlateCarree(),
        zorder=1,
        add_colorbar=False,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        subplot_kws={
            "projection": ccrs.LambertConformal(
                central_longitude=-95, central_latitude=45
            )
        },
    )

    cb = plt.colorbar(cm, shrink=0.5)
    cb.set_label(cb_title)
    ax.set_title(title)

    if fp is not None:
        plt.savefig(fp, dpi=1200)

    return fig, ax


def plot_Europe(
    xr_res, cmap="viridis", vmin=None, vmax=None, title=None, cb_title=None, fp=None
):
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.PlateCarree(), frameon=True)
    ax.patch.set_visible(True)
    ax.set_extent([-12, 31.6, 35, 71.2], ccrs.PlateCarree())

    shapename = "admin_0_countries"
    states_shp = shpreader.natural_earth(
        resolution="110m", category="cultural", name=shapename
    )
    ax.add_geometries(
        shpreader.Reader(states_shp).geometries(),
        ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="gray",
    )

    cm = xr_res.plot(
        transform=ccrs.PlateCarree(),
        zorder=1,
        add_colorbar=False,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        shading="gouraud",
        infer_intervals=False,
    )

    cb = plt.colorbar(cm, shrink=0.5)
    cb.set_label(cb_title)
    ax.set_title(title)

    ax.set_xticks([-10, 0, 10, 20, 30], crs=ccrs.PlateCarree())
    ax.set_yticks([30, 40, 50, 60, 70], crs=ccrs.PlateCarree())

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    if fp is not None:
        plt.savefig(fp, dpi=1200)

    return fig, ax

def meta_KDtree(meta_df, leaf_size=40, fp=None):
    """
    Create a sklearn.neighbors.KDTree for fast geospatial lookup operations.
    Requires Scikit Learn library. Not included in pvdeg depency list.
    
    Parameters:
    -----------
    meta_df: pd.DataFrame
        Dataframe of metadata as generated by pvdeg.weather.get for geospatial
    leaf_size: 
        Number of points at which to switch to brute-force. See sci kit docs.
    fp: str, optional
        Location to save pickled kdtree so we don't have to rebuild the tree.
        If none, no file saved. must be ``.pkl`` file extension.

    Returns:
    --------
    kdtree: sklearn.neighbors.KDTree
        kdtree containing latitude-longitude pairs for quick lookups

    See Also:
    https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KDTree.html
    """

    from sklearn.neighbors import KDTree
    from joblib import dump

    coordinates = meta_df[['latitude', 'longitude']].values
    elevations = meta_df['altitude'].values

    tree = KDTree(coordinates, leaf_size=40)
    
    if fp:
        dump(tree, fp)

    return tree

def _mountains(meta_df, kdtree, index, rad_1, rad_2, threshold_factor, elevation_floor):
    coordinates = meta_df[['latitude', 'longitude']].values
    elevations = meta_df['altitude'].values

    # Reshape the coordinate array to 2D
    query_point = coordinates[index].reshape(1, -1)
    
    # Query the KDTree for neighbors within the specified radii
    area_points = kdtree.query_radius(query_point, r=rad_1)[0]
    local_points = kdtree.query_radius(query_point, r=rad_2)[0]

    # If no area points are found, return False
    if len(area_points) == 0:
        return False

    # Calculate mean elevations for the area and local points
    area_elevations = elevations[area_points]
    local_elevations = elevations[local_points]
    area_mean = np.mean(area_elevations)
    local_mean = np.mean(local_elevations)

    # Determine if the point is a mountain based on the threshold factor
    if local_mean > area_mean * threshold_factor and elevations[index] >= elevation_floor:
        return True
    
    return False

# TODO: coordinate bounding box
def identify_mountains(meta_df, kdtree, rad_1=12, rad_2=1, threshold_factor=1.25, elevation_floor=0):
    """
    Find mountains from elevation metadata using sklearn kdtree for fast lookup.
    Compares a large area of points to a small area of points to find 
    significant changes in elevation representing mountains. Tweak the radii 
    to determine the sensitivity and noise. Bad radii cause the result to 
    become unstable quickly. kdtree can be generated using 
    ``pvdeg.geospatial.meta_KDTree``

    Parameters:
    -----------
    meta_df : pd.DataFrame
        Dataframe of metadata as generated by pvdeg.weather.get for geospatial
    kdtree : sklearn.neighbors.KDTree
        kdtree containing latitude-longitude pairs for quick lookups
        Generate using ``pvdeg.geospatial.meta_KDTree``
    rad_1 : float
        radius of the larger search area whose elevations are compared against
        the smaller search area. controls the kdtree query region.
    rad_2 : float
        radius of the smaller search area whose elevations are compared to the
        larger area. controls the kdtree query region.
    threshold_factor : float
        change the significance level of elevation difference between 
        small and large regions. Higher means terrain must be more extreme to
        register as a mountain. Small changes result in large differences here.
        When the left side of the expression is greater, the datapoint is 
        classified as a mountain.
        ``local mean elevation > broad mean elevation * threshold_factor``
    elevation_floor : int
        minimum inclusive elevation in meters. If a point has smaller location
        it will be clipped from result.
    Returns:
    --------
    meta_df : pd.DataFrame
        Modified dataframe with a new column ``mountain``. Boolean for 
        each entry in the dataframe characterizing mountainous vs flat.
    """

    meta_df.loc[:,'mountain'] = [_mountains(meta_df, kdtree, i, rad_1, rad_2, threshold_factor) for i in range(len(meta_df))]

    return meta_df

# TODO: coordinate bounding box
# bbox = min Longitude , min Latitude , max Longitude , max Latitude 
def feature_downselect(meta_df, kdtree=None, feature_name=None, resolution='10m', radius=None):
    """
    meta_df : pd.DataFrame
        Dataframe of metadata as generated by pvdeg.weather.get for geospatial
    kdtree : sklearn.neighbors.KDTree or str
        kdtree containing latitude-longitude pairs for quick lookups
        Generate using ``pvdeg.geospatial.meta_KDTree``. Can take a pickled
        kdtree as a path to the .pkl file.
    feature : str
        cartopy.feature.NaturalEarthFeature feature key.
        Options: ``'lakes'``, ``'rivers_lake_centerlines'``, ``'coastline'``
    resolution : str
        cartopy.feature.NaturalEarthFeature resolution.
        Options: ``'10m'``, ``'50m'``, ``'110m'``
    radius : float
        Area around feature coordinates to include in the downsampled result. 
        Bigger area means larger radius and more samples included.
    """

    if isinstance(kdtree, str):
        from joblib import load
        kdtree = load(kdtree)

    if radius is None:
        if feature_name == 'coastline':
            radius=1
        elif feature_name in ['river_lake_centerlines', 'lakes']:
            radius=0.1

    feature = cfeature.NaturalEarthFeature('physical', feature_name, resolution)
    feature_geometries = []

    # Collect geometries
    for geom in feature.geometries():
        if isinstance(geom, LineString):
            feature_geometries.append(geom)
        elif isinstance(geom, MultiLineString):
            for line in geom.geoms:  # Correctly access the LineString objects
                feature_geometries.append(line)

    # Extract points from geometries
    feature_points = []
    for geom in feature_geometries:
        coords = list(geom.coords)
        for coord in coords:
            feature_points.append(coord)

    feature_coords = np.array(feature_points, dtype=np.float32)

    meta_df.loc[:,feature_name] = False # this raises an error but works as expected

    include_set = set()
    for coord in feature_coords:
        coord = np.array(coord).reshape(1, -1)  
        flipped_coord = coord[:, [1,0]] # biggest headache of my life to figure out that these were flipped
        indices = kdtree.query_radius(flipped_coord, radius)[0]  
        include_set.update(indices.tolist())

    include_arr = np.fromiter(include_set, dtype=int, count=len(include_set))
    meta_df.iloc[include_arr, meta_df.columns.get_loc(feature_name)] = True

    return meta_df