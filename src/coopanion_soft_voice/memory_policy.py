"""Loading guards for the measured native layouts; units are system available RAM."""

def loading_requirement(config):
    compact = (config.get('compactGraphs') is True and config.get('kvContext') == 1024
               and config.get('speechOnly', {}).get('format') == 1)
    if compact and config.get('streamTextEmbedding') is True:
        if config.get('adaptiveKv') is True and config.get('deviceType') == 'discrete' and config.get('vendorId') == 0x10de:
            return 2.75
        return 3.0
    return 3.25 if compact else 4.0
