#ifndef CRC_H
#define CRC_H

#include <stdint.h>
#include <stddef.h>

uint16_t crc16_ccitt(const uint8_t *data, size_t length);

#endif /* CRC_H */
