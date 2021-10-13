"""
Provides conversions from x,y,z to lon,lat,alt.
"""

import logging
from math import sqrt
from typing import Tuple

import pyproj
from pyproj import Transformer

from core.emulator.enumerations import RegisterTlvs

SCALE_FACTOR: float = 100.0
CRS_WGS84: int = 4326
CRS_PROJ: int = 3857


class GeoLocation:
    """
    Provides logic to convert x,y,z coordinates to lon,lat,alt using
    defined projections.
    """

    name: str = "location"
    config_type: RegisterTlvs = RegisterTlvs.UTILITY

    def __init__(self) -> None:
        """
        Creates a GeoLocation instance.
        """
        self.to_pixels: Transformer = pyproj.Transformer.from_crs(
            CRS_WGS84, CRS_PROJ, always_xy=True
        )
        self.to_geo: Transformer = pyproj.Transformer.from_crs(
            CRS_PROJ, CRS_WGS84, always_xy=True
        )
        self.refproj: Tuple[float, float, float] = (0, 0, 0.0)
        self.refgeo: Tuple[float, float, float] = (0, 0, 0)
        self.refxyz: Tuple[float, float, float] = (0, 0, 0.0)
        self.refscale: float = 1113194

    def setrefgeo(self, lat: float, lon: float, alt: float) -> None:
        """
        Set the geospatial reference point.

        :param lat: latitude reference
        :param lon: longitude reference
        :param alt: altitude reference
        :return: nothing
        """
        self.refgeo = (lat, lon, alt)
        px, py = self.to_pixels.transform(lon, lat)
        self.refproj = (px, py, alt)

    def reset(self) -> None:
        """
        Reset reference data to default values.

        :return: nothing
        """
        self.refxyz = (0.0, 0.0, 0.0)
        self.refgeo = (0.0, 0.0, 0.0)
        self.refscale = 1.0
        self.refproj = self.to_pixels.transform(*self.refgeo)

    def pixels2meters(self, value: float) -> float:
        """
        Provides conversion from pixels to meters.

        :param value: pixels value
        :return: pixels value in meters
        """
        return (value / SCALE_FACTOR) * self.refscale

    def meters2pixels(self, value: float) -> float:
        """
        Provides conversion from meters to pixels.

        :param value: meters value
        :return: meters value in pixels
        """
        if self.refscale == 0.0:
            return 0.0
        return SCALE_FACTOR * (value / self.refscale)

    def getxyz(self, lat: float, lon: float, alt: float) -> Tuple[float, float, float]:
        """
        Convert provided lon,lat,alt to x,y,z.

        :param lat: latitude value
        :param lon: longitude value
        :param alt: altitude value
        :return: x,y,z representation of provided values
        """
        logging.debug("input lon,lat,alt(%s, %s, %s)", lon, lat, alt)
        px, py = self.to_pixels.transform(lon, lat)
        px -= self.refproj[0]
        py -= self.refproj[1]
        pz = alt - self.refproj[2]
        x = self.meters2pixels(px) + self.refxyz[0]
        y = -(self.meters2pixels(py) + self.refxyz[1])
        z = self.meters2pixels(pz) + self.refxyz[2]
        logging.debug("result x,y,z(%s, %s, %s)", x, y, z)
        return x, y, z

    def getgeo(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """
        Convert provided x,y,z to lon,lat,alt.

        :param x: x value
        :param y: y value
        :param z: z value
        :return: lat,lon,alt representation of provided values
        """
        logging.debug("input x,y(%s, %s)", x, y)
        x -= self.refxyz[0]
        y = -(y - self.refxyz[1])
        if z is None:
            z = self.refxyz[2]
        else:
            z -= self.refxyz[2]
        px = self.refproj[0] + self.pixels2meters(x)
        py = self.refproj[1] + self.pixels2meters(y)
        lon, lat = self.to_geo.transform(px, py)
        alt = self.refgeo[2] + self.pixels2meters(z)
        logging.debug("result lon,lat,alt(%s, %s, %s)", lon, lat, alt)
        return lat, lon, alt


def main():
    geo = GeoLocation()
    geo.setrefgeo(85.051117, -180, 0)

    x, y, z = geo.getxyz(0, 0, 0)
    # print(f"px={geo.refproj[0]},py={geo.refproj[1]},alt={geo.refproj[2]}")
    # x = validate_xyz(x)
    # y = validate_xyz(y)
    # z = validate_xyz(z)
    print(x, y, z)
    x, y, z = geo.getgeo(x, y, z)
    print(x, y, z)
    nodes_path = "/home/hyh/core/daemon/core/location/test.nodes"
    file = open(nodes_path, "r", encoding="utf8", errors="ignore")
    newfile_path = nodes_path[:-6] + ".ns"
    file2 = open(newfile_path, "w", encoding="utf8", errors="ignore")

    strs = file.readlines()
    maxnodenum = 52  # 最大节点数量
    # lastTime = [-1][0.0, 0.0, 0.0] * (maxnodenum + 1)  #前一个时间
    # lastdata = [[-1.0, 0.0, 0.0, 0.0]] * (maxnodenum + 1)
    lastdata = []
    for i in range(maxnodenum + 1):
        lastdata.append([])
        for j in range(4):
            lastdata[i].append(-1)
    for stri in strs:
        str_elements = stri.split(" ")  # 以空格为分界划分元素
        nodeid = int(str_elements[0])  # 节点号

        if str_elements[1] == "0":
            time = 0
            # lastTime[nodeid] = time
            lastdata[nodeid][0] = time
        else:
            time = int(str_elements[1][0:-1:1])

            # newtime = lastTime[nodeid]
            # lastTime[nodeid] = time
            newtime = lastdata[nodeid][0]
            lastdata[nodeid][0] = time

        lon = float(str_elements[2][1:-1:1])  # 经度
        lat = float(str_elements[3][0:-1:1])  # 纬度
        alt = float(str_elements[4][0:-1:1])

        # print(nodeid, time, lon, lat, alt)
        x, y, z = geo.getxyz(lat, lon, alt)
        x = validate_xyz(x)
        y = validate_xyz(y)
        z = validate_xyz(z)
        # print(x,y,z)
        if time == 0:
            lastdata[nodeid][1] = x
            lastdata[nodeid][2] = y
            lastdata[nodeid][3] = z
            newstr = (
                "$node_("
                + str(nodeid)
                + ") set X_ "
                + str(x)
                + "\n"
                + "$node_("
                + str(nodeid)
                + ") set Y_ "
                + str(y)
                + "\n"
                + "$node_("
                + str(nodeid)
                + ") set Z_ "
                + str(z)
                + "\n"
            )
            # print(newstr)
        else:
            newx = lastdata[nodeid][1]
            newy = lastdata[nodeid][2]
            newz = lastdata[nodeid][3]
            speed = sqrt(pow(newx - x, 2) + pow(newy - y, 2) + pow(newz - z, 2)) / (
                time - newtime
            )
            lastdata[nodeid][1] = x
            lastdata[nodeid][2] = y
            lastdata[nodeid][3] = z
            newstr = (
                "$ns_ at "
                + str(newtime)
                + ' "$node_('
                + str(nodeid)
                + ") "
                + "setdest "
                + str(x)
                + " "
                + str(y)
                + " "
                + str(z)
                + " "
                + str(speed)
                + '"\n'
            )
            # print(newstr)

        file2.writelines(newstr)

    file.close()

    file2.close()


def validate_xyz(num: float) -> float:
    if num < 0:
        return 0
    return num


if __name__ == "__main__":
    main()
