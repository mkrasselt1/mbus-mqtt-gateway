"""
Zentrale Logging-Konfiguration für MBus Gateway
Automatische Erkennung: Konsole vs. Windows Service
Überschreibt print() automatisch für Service-Modus
"""
import logging
import os
import sys
import builtins

# Globale Variable zur Erkennung ob als Service
_is_service = None
_logger_initialized = False
_original_print = print

def is_running_as_service():
    """
    Erkennt ob das Script als Windows Service läuft
    
    Returns:
        bool: True wenn als Service, False wenn in Konsole
    """
    global _is_service
    
    if _is_service is not None:
        return _is_service
    
    try:
        # Prüfe ob stdout verfügbar und ein TTY ist
        if sys.stdout is None:
            _is_service = True
        elif not hasattr(sys.stdout, 'isatty'):
            _is_service = True
        else:
            try:
                _is_service = not sys.stdout.isatty()
            except:
                _is_service = True
    except Exception:
        _is_service = True
    
    return _is_service

def setup_app_logging():
    """
    Konfiguriert Logging für alle App-Module
    Nur als Service aktiv - in Konsole werden print() Statements verwendet
    """
    global _logger_initialized
    
    if _logger_initialized:
        return
    
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    from logging.handlers import TimedRotatingFileHandler
    # Tägliche Rotation, maximal 5 Dateien behalten
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, 'gateway.log'),
        when='midnight',
        interval=1,
        backupCount=5,
        encoding='utf-8',
        utc=True
    )
    handlers = [file_handler]
    
    # Als Service: Nur File-Handler
    # In Konsole: Zusätzlich StreamHandler für Debugging
    is_service = is_running_as_service()
    
    if not is_service:
        # In Konsole: StreamHandler hinzufügen (für optionales Debug-Logging)
        try:
            if sys.stdout is not None:
                handlers.append(logging.StreamHandler(sys.stdout))
        except Exception:
            pass
    else:
        # Als Service: Überschreibe print() mit Logging
        _replace_print_with_logging()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True  # Überschreibe existierende Konfiguration
    )
    
    # Externe Libraries auf WARNING setzen
    logging.getLogger('meterbus').setLevel(logging.WARNING)
    logging.getLogger('serial').setLevel(logging.WARNING)
    logging.getLogger('paho').setLevel(logging.WARNING)
    
    _logger_initialized = True

def _replace_print_with_logging():
    """
    Ersetzt die built-in print() Funktion mit Logging
    Nur im Service-Modus aktiv!
    """
    def print_to_log(*args, **kwargs):
        """Ersatz für print() der ins Log schreibt"""
        try:
            # Konvertiere alle Argumente zu String
            message = ' '.join(str(arg) for arg in args)
            
            # Ins Log schreiben
            logger = logging.getLogger('MBusGateway.print')
            logger.info(message)
        except Exception as e:
            # Fallback: Nichts tun wenn Logging fehlschlägt
            pass
    
    # Überschreibe die built-in print Funktion
    try:
        builtins.print = print_to_log
    except Exception:
        # Wenn Override fehlschlägt, weitermachen
        pass

def get_logger(name):
    """
    Gibt einen Logger für das angegebene Modul zurück
    
    Args:
        name: Name des Moduls (z.B. 'mbus', 'mqtt', 'device_manager')
    
    Returns:
        logging.Logger: Logger-Instanz
    """
    return logging.getLogger(f'MBusGateway.{name}')

def log_or_print(message, level='info'):
    """
    Intelligente Ausgabe: print() in Konsole, logging als Service
    
    Args:
        message: Die auszugebende Nachricht
        level: Log-Level ('info', 'warning', 'error', 'debug')
    """
    if is_running_as_service():
        # Als Service: Logging verwenden
        logger = logging.getLogger('MBusGateway')
        log_func = getattr(logger, level, logger.info)
        log_func(message)
    else:
        # In Konsole: print() verwenden
        level_prefix = {
            'info': '[INFO]',
            'warning': '[WARN]',
            'error': '[ERROR]',
            'debug': '[DEBUG]'
        }.get(level, '[INFO]')
        print(f"{level_prefix} {message}")
        
        # Zusätzlich auch ins Log schreiben
        if _logger_initialized:
            logger = logging.getLogger('MBusGateway')
            log_func = getattr(logger, level, logger.info)
            log_func(message)
