"""Loading guards for the measured native layouts; units are system available RAM."""

def loading_requirement(config):
    compact = (config.get('compactGraphs') is True and config.get('kvContext') == 1024
               and config.get('speechOnly', {}).get('format') == 1)
    return 3.5 if compact else 4.0
