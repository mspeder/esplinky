"""Utility to parse and validate a Linky TeleInformation Client (TIC) frame."""

import logging

_LOGGER = logging.getLogger(__name__)

def validate_checksum(line: str) -> bool:
    """Validate the checksum of a single TIC data line."""
    # A TIC line looks like: LABEL VALUE CHECKSUM
    
    # 1. Check for the mandatory line structure (LABEL + VALUE + SPACE + CHECKSUM)
    # The checksum is the last character, separated by a space from the data
    if len(line) < 3 or line[-2] != ' ':
        return False
        
    # 2. Extract data to be checksummed (everything up to the space before the checksum)
    # The data includes the line termination character (e.g., CR or LF) if present.
    checksum_char = line[-1]
    data_to_sum = line[:-2] 
    
    # 3. Calculate the sum of ASCII codes for all characters in the data block
    checksum_value = sum(ord(char) for char in data_to_sum)
    
    # 4. Calculate the ASCII code of the expected checksum character (modulo 64, then offset by 32)
    expected_checksum = chr((checksum_value & 0x3F) + 0x20)
    
    return expected_checksum == checksum_char

def parse_tic_frame(raw_frame: bytes) -> dict[str, str]:
    """
    Parses a full TIC frame (Historic Mode) and returns valid, extracted values.
    
    Args:
        raw_frame: The raw bytes received over UDP (a full TIC frame).

    Returns:
        A dictionary mapping validated Linky labels (e.g., 'BASE', 'PAPP') to their values (e.g., '12345678', '1250').
    """
    # Decoding common for Linky: ASCII
    try:
        frame_str = raw_frame.decode('ascii').strip()
    except UnicodeDecodeError:
        _LOGGER.error("Failed to decode raw TIC frame using ASCII.")
        return {}

    # Split the frame into individual data lines
    # Data lines are typically separated by CR (0x0D) or LF (0x0A)
    lines = frame_str.replace('\r', '\n').split('\n')
    
    extracted_data = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 1. Validate Checksum
        if not validate_checksum(line):
            # Log failure but continue processing other lines
            _LOGGER.warning("Invalid checksum for TIC line: '%s'", line)
            continue
            
        # 2. Extract Label and Value
        # A valid line looks like: ADCO 01234567890C
        
        # Strip the checksum and the preceding space
        data_part = line[:-2]
        
        # Split by space. Historic mode uses a single space delimiter.
        parts = data_part.split(' ', 1)
        
        if len(parts) == 2:
            label = parts[0].strip()
            value = parts[1].strip()
            
            # Label must be non-empty and non-data start/end delimiters
            if label and value and label not in ('\x02', '\x03'):
                extracted_data[label] = value
        
    return extracted_data
