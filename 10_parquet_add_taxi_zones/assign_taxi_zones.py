#!/usr/bin/env python

import dask
from dask import delayed
from dask.distributed import Client

import os
import dask.dataframe as dd
import json
import numpy as np
import pandas as pd
import geopandas
from shapely.geometry import Point


def assign_taxi_zones(df, lon_var, lat_var, locid_var):
    """Joins DataFrame with Taxi Zones shapefile.

    This function takes longitude values provided by `lon_var`, and latitude
    values provided by `lat_var` in DataFrame `df`, and performs a spatial join
    with the NYC taxi_zones shapefile. 

    The shapefile is hard coded in, as this function makes a hard assumption of
    latitude and longitude coordinates. It also assumes latitude=0 and 
    longitude=0 is not a datapoint that can exist in your dataset. Which is 
    reasonable for a dataset of New York, but bad for a global dataset.

    Only rows where `df.lon_var`, `df.lat_var` are reasonably near New York,
    and `df.locid_var` is set to np.nan are updated. 

    Parameters
    ----------
    df : pandas.DataFrame or dask.DataFrame
        DataFrame containing latitudes, longitudes, and location_id columns.
    lon_var : string
        Name of column in `df` containing longitude values. Invalid values 
        should be np.nan.
    lat_var : string
        Name of column in `df` containing latitude values. Invalid values 
        should be np.nan
    locid_var : string
        Name of column in `df` containing taxi_zone location ids. Rows with
        valid, nonzero values are not overwritten. 
    """

    localdf = df[[lon_var, lat_var, locid_var]].copy()
    localdf = localdf.reset_index()
    localdf[lon_var] = localdf[lon_var].fillna(value=0.)
    localdf[lat_var] = localdf[lat_var].fillna(value=0.)
    localdf['replace_locid'] = (localdf[locid_var].isnull()
                                & (localdf[lon_var] != 0.)
                                & (localdf[lat_var] != 0.))

    if (np.any(localdf['replace_locid'])):
        shape_df = geopandas.read_file('../shapefiles/taxi_zones_latlon.shp')
        shape_df.drop(['OBJECTID', "Shape_Area", "Shape_Leng", "borough", "zone"],
                      axis=1, inplace=True)

        try:
            local_gdf = geopandas.GeoDataFrame(
                localdf, crs={'init': 'epsg:4326'},
                geometry=[Point(xy) for xy in
                          zip(localdf[lon_var], localdf[lat_var])])
            local_gdf = geopandas.sjoin(
                local_gdf, shape_df, how='left', op='intersects')

            local_gdf.LocationID.values[~local_gdf.replace_locid] = (
                (local_gdf[locid_var])[~local_gdf.replace_locid]).values
            return local_gdf.LocationID.rename(locid_var)
        except ValueError as ve:
            print(ve)
            print(ve.stacktrace())
            return df[locid_var]

    else:
        return df[locid_var]


def main(client):
    green = dd.read_parquet('/data/green.parquet')
    green = green.reset_index(drop=True)
    for i in range(54, green.npartitions):
        df = green.get_partition(i).compute()
        
    
        df['dropoff_location_id'] = assign_taxi_zones(
            df, "dropoff_longitude", "dropoff_latitude",
            "dropoff_location_id")
        df['pickup_location_id'] = assign_taxi_zones(
            df, "pickup_longitude", "pickup_latitude",
            "pickup_location_id")

        df.to_hdf('/data/green_{0:04d}.hdf'.format(i), '/data', format='t', complib='blosc', complevel=1)

    yellow = dd.read_parquet('/data/yellow.parquet')
    yellow = yellow.reset_index(drop=True)
    for i in range(yellow.npartitions):
        df = yellow.get_partition(i).compute()
    
        df['dropoff_location_id'] = assign_taxi_zones(
            df, "dropoff_longitude", "dropoff_latitude",
            "dropoff_location_id")
        df['pickup_location_id'] = assign_taxi_zones(
            df, "pickup_longitude", "pickup_latitude",
            "pickup_location_id")

        df.to_hdf('/data/yellow_{0:04d}.hdf'.format(i), '/data', format='t', complib='blosc', complevel=1)
        


    return

if __name__ == '__main__':

    
    client = None
    main(client)
