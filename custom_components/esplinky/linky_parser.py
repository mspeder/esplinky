"""TIC (Téléinformation Client) frame parsing and checksum validation."""

import logging

_LOGGER = logging.getLogger(__name__)

# Start-of-frame: 0x02, End-of-frame: 0x03, Separator: 0x0D 0x0A (CR LF)
FRAME_START = b'\x02'
FRAME_END = b'\x03'
LINE_SEPARATOR = b'\r\n'

def calculate_checksum(data_line: str) -> str:
    """
    Calculates the 7-bit ASCII checksum for a TIC line.
    The checksum is the sum of the ASCII codes of all characters
    in the data_line, modulo 64, offset by 0x20 (' ').
    """
    checksum_value = 0
    
    for char in data_line:
        checksum_value += ord(char)
        
    checksum_value = (checksum_value & 0x3F) + 0x20
    return chr(checksum_value)


def parse_tic_frame(raw_bytes: bytes) -> dict[str, str]:
    """
    Parses a raw Linky TIC frame, validates checksums, and returns valid data.
    
    Args:
        raw_bytes: The raw UDP packet content (should contain the full TIC frame).
        
    Returns:
        A dictionary of validated {label: value} pairs.
    """
    
    try:
        # Find the frame boundaries (0x02 and 0x03)
        start_index = raw_bytes.find(FRAME_START)
        end_index = raw_bytes.find(FRAME_END)
        
        if start_index == -1 or end_index == -1 or end_index < start_index:
            _LOGGER.warning("Invalid TIC frame boundaries (STX/ETX not found).")
            return {}

        # Extract the content between STX and ETX
        frame_content = raw_bytes[start_index + 1 : end_index].strip()
        
    except Exception as e:
        _LOGGER.error("Error processing raw bytes: %s", e)
        return {}
    
    # Decode the extracted content
    try:
        # Linky Historic mode uses ISO-8859-1 or 7-bit ASCII
        frame_str = frame_content.decode("iso-8859-1")
    except UnicodeDecodeError as e:
        _LOGGER.error("Failed to decode TIC frame content: %s", e)
        return {}

    valid_data: dict[str, str] = {}
    
    # The frame content is split by CR LF (\r\n)
    lines = frame_str.split('\r\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # The line structure is: [Data to Checksum] [Checksum Character]
        # Example: IINST 018 P
        
        # Find the index of the space before the checksum character
        last_space_index = line.rfind(' ')
        
        if last_space_index == -1:
            _LOGGER.warning("Could not find checksum space separator in line: %s", line)
            continue
            
        # The data to be checksummed is the entire line up to (and including) the last space
        # This is where the correction is made: including the space before the checksum character.
        data_to_checksum = line[:last_space_index + 1] 
        received_checksum = line[last_space_index + 1] # The checksum character itself

        calculated_checksum = calculate_checksum(data_to_checksum)
        
        if calculated_checksum == received_checksum:
            # Checksum valid. Extract label and value from the data_to_checksum string.
            parts = data_to_checksum.strip().split(' ')
            
            if len(parts) >= 2:
                label = parts[0]
                # In Historic mode, the value is typically the last element of the data fields
                value = parts[-1] 
                valid_data[label] = value
            else:
                _LOGGER.debug("Skipping line with unexpected format after checksum validation: %s", line)
                
        else:
            # We log the data that failed the checksum, which helps debugging the source.
            _LOGGER.warning(
                "Invalid checksum for TIC line: '%s' (Received: '%s', Calculated: '%s'). Source issue.",
                data_to_checksum.strip(), received_checksum, calculated_checksum
            )

    return valid_data
