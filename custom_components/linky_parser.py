"""Utility to parse a raw Linky TIC historic mode frame and validate checksums."""

import logging

_LOGGER = logging.getLogger(__name__)

# Constants for Linky TIC Historic Mode Parsing
# The frame is composed of lines (group of labels) separated by line feed (LF, \n).
# Each group is structured as: LABEL[SPACE]VALUE[SPACE]CHECKSUM[CR]
TIC_FRAME_DELIMITER = b'\n'
TIC_FIELD_SEPARATOR = b' '
TIC_CHECKSUM_SIZE = 1 # Checksum is a single character

def calculate_checksum(data: bytes) -> bytes:
    """
    Calculates the Linky TIC checksum for a given data block (LABEL and VALUE, including spaces).
    The checksum is the sum of all bytes modulo 64, then offset by 32 (ASCII 32 to 95).
    """
    checksum_value = 0
    for byte in data:
        checksum_value += byte

    # Checksum calculation: (sum of bytes) % 64 + 32
    checksum_byte = (checksum_value % 64) + 32
    return chr(checksum_byte).encode('ascii')

def parse_tic_frame(raw_data: bytes) -> dict:
    """
    Parses a raw TIC frame, validates checksums, and returns a dictionary of valid values.
    
    Args:
        raw_data: The raw bytes received from the UDP socket.
        
    Returns:
        A dictionary {label: value} of all data with valid checksums.
    """
    valid_data = {}
    
    # 1. Clean the data (remove potential leading/trailing garbage, frame start/end markers)
    # The TIC frame often starts with STX (\x02) and ends with ETX (\x03). 
    # The split handles the LF (\n) delimiters.
    lines = raw_data.strip().strip(b'\x02\x03').split(TIC_FRAME_DELIMITER)

    for line in lines:
        # Strip Carriage Return (CR, \r) if present
        line = line.strip(b'\r')
        if not line:
            continue

        try:
            # 2. Separate data block from checksum
            # The checksum is the very last byte of the line.
            data_block = line[:-TIC_CHECKSUM_SIZE]
            received_checksum = line[-TIC_CHECKSUM_SIZE:]
            
            # 3. Calculate expected checksum
            expected_checksum = calculate_checksum(data_block)

            # 4. Validate checksum
            if received_checksum != expected_checksum:
                _LOGGER.warning(
                    "Checksum failed for line '%s'. Received: %s, Expected: %s",
                    line.decode('ascii', 'ignore'),
                    received_checksum.decode('ascii'),
                    expected_checksum.decode('ascii')
                )
                continue

            # Checksum is valid. Extract label and value.
            parts = data_block.split(TIC_FIELD_SEPARATOR, 1)
            if len(parts) == 2:
                label = parts[0].decode('ascii').strip()
                value = parts[1].decode('ascii').strip()
                
                # Attempt to convert value to a number if possible
                try:
                    valid_data[label] = int(value)
                except ValueError:
                    try:
                        valid_data[label] = float(value)
                    except ValueError:
                        valid_data[label] = value
            
        except IndexError:
            _LOGGER.error("Malformed TIC line (too short): %s", line.decode('ascii', 'ignore'))
        except Exception as e:
            _LOGGER.error("Error processing line %s: %s", line.decode('ascii', 'ignore'), e)

    return valid_data

