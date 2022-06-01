"""
自定义 emane model 示例
"""
from pathlib import Path
from typing import Dict, Optional, Set, List

from core.config import Configuration
from core.emane import emanemanifest, emanemodel


class ExampleModel(emanemodel.EmaneModel):
    """
    :参数 name: 定义将显示在GUI中的emane模型名称，必须加上前缀 emane_
	:参数 config_ignore: 忽略 mac phy 参数的列表，添加至此列表的参数将不会序列化至emane配置xml中，这些配置一般是core的界面或其他额外设定
    
    Mac 定义:
    :参数 mac_library: 定义模型将引用的 emane MAC库
    :参数 mac_xml: 定义将被解析以获得默认配置选项的MAC清单xml，将显示在GUI中
    :参数 mac_defaults: 覆盖上述的mac层默认值
    :参数 mac_config: 解析xml并转换生成的core支持的列表

    Phy 定义:
    phy一般配置为通用模型，如下所示，下面的参数都是可选的。
    :参数 phy_library: 定义模型将引用的phy库，也可使用自定义phy
    :参数 phy_xml: 定义将被解析以获得配置选项的phy清单xml，将显示在GUI中
    :参数 phy_defaults: 覆盖上述的phy层默认值
    :参数 phy_config: 解析xml并转换生成的core支持的列表
    """

    # 一定为emane_前缀
    name: str = "emane_myrfpipe" 
    # 设置mac库模型
    mac_library: str = "myrfpipemaclayer" 
    # 解析获取模型所有配置
    mac_xml: str = "/usr/share/emane/manifest/myrfpipemaclayer.xml" 
    # 覆盖默认值
    mac_defaults: Dict[str, str] = { 
        "pcrcurveuri": "/usr/share/emane/xml/models/mac/myrfpipe/myrfpipepcr.xml"
    }
    mac_config: List[Configuration] = []

    # phy 类似mac配置，使用默认phy模型 无需设置library
    phy_library: Optional[str] = None
    phy_xml: str = "/usr/share/emane/manifest/emanephy.xml"
    phy_defaults: Dict[str, str] = {
        "subid": "1",
        "propagationmodel": "2ray",
        "noisemode": "none",
    }
    phy_config: List[Configuration] = []
    config_ignore: Set[str] = set()

    @classmethod
    def load(cls, emane_prefix: Path) -> None:
        """
        Called after being loaded within the EmaneManager. Provides configured
        emane_prefix for parsing xml files.

        :param emane_prefix: configured emane prefix path
        :return: nothing
        """
        # load mac configuration
        cls.mac_config = emanemanifest.parse(cls.mac_xml, cls.mac_defaults)
        # load phy configuration
        cls.phy_config = emanemanifest.parse(cls.phy_xml, cls.phy_defaults)
