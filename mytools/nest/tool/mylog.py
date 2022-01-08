import logging, os


def config(log_path, file_level, console_level):
    '''
    配置log, logger是日志对象，handler是流处理器，console是控制台输出
    
    :param log_path: 为日志文件路径
    :param file_level: 设定日志文件debug等级
    :param console_level: 设置控制台
    '''
    # 获取logger对象,取名 logging_name
    logger = logging.getLogger("logging_name")
    # 基准过滤，针对所有输出的第一层过滤
    logger.setLevel(level=logging.DEBUG)
    # 获取文件日志句柄并设置日志级别，第二层过滤
    handler = logging.FileHandler(log_path, encoding='UTF-8')
    handler.setLevel(file_level)
    # 生成并设置文件日志格式
    formatter = logging.Formatter('%(asctime)s %(levelname)s - %(module)s:%(funcName)s - %(message)s')
    handler.setFormatter(formatter)
    # console相当于控制台输出，handler文件输出。获取流句柄并设置日志级别，第二层过滤
    console = logging.StreamHandler()
    console.setLevel(console_level)
    # 为logger对象添加句柄
    logger.addHandler(handler)
    logger.addHandler(console)
    return logger

Nest_path: str = os.path.dirname(os.path.split(__file__)[0])
log_path: str = os.path.join(Nest_path, "nest.log")
scenario_path: str = os.path.join(Nest_path, "xmls")
nest_config:str = os.path.join(Nest_path, "nest_config")

logger = config(log_path, logging.INFO, logging.INFO)

if __name__ == "__main__":
    # logging = config("./nest.log", logging.DEBUG, logging.DEBUG)
    logger.debug("This is a debug log.")
    logger.info("This is a info log.")
    logger.warning("This is a warning log.")
    logger.error("This is a error log.")
    logger.critical("This is a critical log.")
