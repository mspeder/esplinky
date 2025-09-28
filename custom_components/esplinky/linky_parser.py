"""Utility to parse and validate a Linky TeleInformation Client (TIC) frame."""

import logging

_LOGGER = logging.getLogger(__name__)

def validate_checksum(line: str) -> bool:
    """Validate the checksum of a single TIC data line with detailed troubleshooting."""
    # A TIC line looks like: LABEL VALUE CHECKSUM
    
    # 1. Check basic line structure
    if len(line) < 3:
        _LOGGER.debug("Checksum validation failed: Line too short (%d chars): '%s'", len(line), repr(line))
        return False
    
    # Check if line has the expected format with space before checksum
    if line[-2] != ' ':
        # Special handling for lines that might be truncated or malformed
        _LOGGER.warning(
            "Checksum validation failed: No space before checksum\n"
            "  Line: '%s'\n"
            "  Length: %d chars\n"
            "  Last 5 chars: '%s'\n"
            "  ASCII codes of last 5 chars: %s\n"
            "  Expected format: 'LABEL VALUE CHECKSUM' (space before last char)",
            line,
            len(line),
            repr(line[-5:]) if len(line) >= 5 else repr(line),
            [ord(c) for c in line[-5:]] if len(line) >= 5 else [ord(c) for c in line]
        )
        return False
        
    # 2. Extract components for debugging
    checksum_char = line[-1]
    data_to_sum = line[:-2]  # Everything except space and checksum
    
    # 3. Calculate the sum of ASCII codes
    checksum_value = sum(ord(char) for char in data_to_sum)
    
    # 4. Calculate expected checksum using TIC formula
    expected_checksum_code = (checksum_value & 0x3F) + 0x20
    expected_checksum = chr(expected_checksum_code)
    
    # 5. Compare checksums
    is_valid = expected_checksum == checksum_char
    
    if not is_valid:
        # Detailed troubleshooting information
        _LOGGER.warning(
            "Checksum validation failed for TIC line: '%s'\n"
            "  Data part: '%s'\n"
            "  Data length: %d\n" 
            "  Data ASCII codes: %s\n"
            "  Sum of ASCII codes: %d (0x%X)\n"
            "  Sum & 0x3F: %d (0x%02X)\n"
            "  Expected checksum code: %d (0x%02X)\n"
            "  Expected checksum char: '%s' (ASCII %d)\n"
            "  Received checksum char: '%s' (ASCII %d)\n"
            "  Difference: %d",
            repr(line),
            repr(data_to_sum),
            len(data_to_sum),
            [ord(c) for c in data_to_sum],
            checksum_value,
            checksum_value,
            checksum_value & 0x3F,
            checksum_value & 0x3F,
            expected_checksum_code,
            expected_checksum_code,
            expected_checksum,
            ord(expected_checksum),
            checksum_char,
            ord(checksum_char),
            ord(checksum_char) - ord(expected_checksum)
        )
        
        # Additional analysis for common issues
        if '\r' in line or '\n' in line:
            _LOGGER.warning("Line contains CR/LF characters that may affect checksum calculation")
        
        if len(data_to_sum.split()) < 2:
            _LOGGER.warning("Line doesn't appear to have LABEL VALUE structure")
            
        # Check if it might be a different TIC format (Standard mode vs Historic mode)
        if '\t' in data_to_sum:
            _LOGGER.warning("Line contains TAB characters - might be Standard mode TIC format")
    else:
        _LOGGER.debug("Checksum validation passed for line: '%s'", repr(line))
    
    return is_valid

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
        _LOGGER.debug("Successfully decoded TIC frame (%d bytes) to ASCII string (%d chars)", 
                     len(raw_frame), len(frame_str))
    except UnicodeDecodeError as e:
        _LOGGER.error("Failed to decode raw TIC frame using ASCII: %s", e)
        # Try with error handling to see partial content
        try:
            frame_str = raw_frame.decode('ascii', errors='replace').strip()
            _LOGGER.debug("Partial decode with replacement chars: '%s'", repr(frame_str[:100]))
        except Exception:
            pass
        return {}

    # Log raw frame for debugging if it's small enough
    if len(frame_str) < 500:
        _LOGGER.debug("Raw TIC frame content: %s", repr(frame_str))
    else:
        _LOGGER.debug("Raw TIC frame content (first 200 chars): %s...", repr(frame_str[:200]))

    # Split the frame into individual data lines
    # Data lines are typically separated by CR (0x0D) or LF (0x0A)
    original_lines = frame_str.replace('\r', '\n').split('\n')
    lines = [line.strip() for line in original_lines if line.strip()]
    
    _LOGGER.debug("Split frame into %d non-empty lines", len(lines))
    
    # Log each line before processing to help identify malformed lines
    for i, line in enumerate(lines):
        _LOGGER.debug("Line %d: length=%d, content='%s', last_5_chars='%s'", 
                     i+1, len(line), line, repr(line[-5:]) if len(line) >= 5 else repr(line))
    
    extracted_data = {}
    valid_lines = 0
    invalid_lines = 0

    for i, line in enumerate(lines):
        if not line:
            continue
            
        _LOGGER.debug("Processing line %d: %s", i+1, repr(line))
        
        # Check for obviously malformed lines before checksum validation
        if not line or len(line) < 3:
            _LOGGER.warning("Skipping malformed line %d: too short (%d chars): '%s'", i+1, len(line), line)
            invalid_lines += 1
            continue
            
        # Check if line ends with multiple spaces (possible transmission issue)
        if line.endswith('  ') or line.endswith('\t'):
            _LOGGER.warning("Line %d has suspicious trailing whitespace: '%s' (may be truncated)", i+1, repr(line))
            
        # 1. Try to extract Label and Value first (works for both valid and invalid checksums)
        # Determine data part based on line structure
        if len(line) >= 3 and line[-2] == ' ':
            # Standard format: LABEL VALUE CHECKSUM
            data_part = line[:-2]
        else:
            # Malformed line (no checksum): LABEL VALUE
            data_part = line
            
        # Split by space. Historic mode uses a single space delimiter.
        parts = data_part.split(' ', 1)
        
        if len(parts) == 2:
            label = parts[0].strip()
            value = parts[1].strip()
            
            # Clean trailing dots from specific labels that commonly have them
            if label in ('PTEC', 'OPTARIF'):
                original_value = value
                value = value.rstrip('.')
                if original_value != value:
                    _LOGGER.debug("Cleaned trailing dots from %s: '%s' -> '%s'", 
                                 label, original_value, value)
            
            # Label must be non-empty and non-data start/end delimiters
            if label and value and label not in ('\x02', '\x03'):
                # 2. Validate Checksum (only for properly formatted lines)
                if len(line) >= 3 and line[-2] == ' ':
                    if not validate_checksum(line):
                        invalid_lines += 1
                        # Only accept PTEC and OPTARIF values without valid checksums
                        if label in ('PTEC', 'OPTARIF'):
                            _LOGGER.warning("Invalid checksum for TIC line %d: '%s' - but accepting %s value '%s'", 
                                           i+1, line, label, value)
                        else:
                            _LOGGER.warning("Invalid checksum for TIC line %d: '%s' - rejecting %s value", 
                                           i+1, line, label)
                            continue
                    else:
                        valid_lines += 1
                else:
                    # Line without proper checksum format
                    invalid_lines += 1
                    # Only accept PTEC and OPTARIF values without checksum format
                    if label in ('PTEC', 'OPTARIF'):
                        _LOGGER.warning("Line %d missing checksum: '%s' - but accepting %s value '%s'", 
                                       i+1, line, label, value)
                    else:
                        _LOGGER.warning("Line %d missing checksum: '%s' - rejecting %s value", 
                                       i+1, line, label)
                        continue
                
                # If we reach here, the value should be extracted
                extracted_data[label] = value
                _LOGGER.debug("Successfully extracted: %s = %s", label, value)
            else:
                _LOGGER.debug("Skipped line with empty label/value or delimiter: label='%s', value='%s'", 
                             label, value)
        else:
            invalid_lines += 1
            _LOGGER.warning("Line %d has unexpected format: '%s' -> parts: %s", 
                           i+1, line, parts)
    
    _LOGGER.info("TIC frame parsing complete: %d valid lines, %d invalid lines, %d extracted values", 
                valid_lines, invalid_lines, len(extracted_data))
    
    if invalid_lines > 0:
        _LOGGER.warning("Frame had %d lines with checksum errors out of %d total lines (%.1f%% failure rate)", 
                       invalid_lines, len(lines), (invalid_lines / len(lines)) * 100 if lines else 0)
    
    return extracted_data