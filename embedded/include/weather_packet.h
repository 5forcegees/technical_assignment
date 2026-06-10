#ifndef WEATHER_PACKET_H
#define WEATHER_PACKET_H

#include <stdint.h>
#include <stdbool.h>
#include "weather_types.h"

/*
 * Serialise a WeatherPacket to an 11-byte buffer.
 * Computes and appends CRC-16/CCITT before writing.
 * buf must be at least WEATHER_PACKET_SIZE bytes.
 */
void weather_packet_serialize(const WeatherPacket *pkt, uint8_t *buf);

/*
 * Deserialise 11 bytes into a WeatherPacket.
 * Returns true if CRC validates, false otherwise.
 */
bool weather_packet_deserialize(const uint8_t *buf, WeatherPacket *pkt);

/* Build a WeatherPacket from a sensor reading. */
WeatherPacket weather_packet_create(uint16_t device_id, uint32_t timestamp,
                                    int8_t temperature, uint8_t humidity);

#endif /* WEATHER_PACKET_H */
