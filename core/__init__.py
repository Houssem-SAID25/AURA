"""
core package – command parsing, intent detection, command registry, and action execution.

Modules
-------
command_parser    NLP classifier: turns raw text into structured command dicts.
command_registry  Dynamic registry: loads compound commands from config/commands.json.
intent_detector   Fuzzy intent detection: identifies what the user wants to do.
action_handler    Execution engine: dispatches commands to integration modules.
"""
