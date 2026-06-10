#include <string.h>
#include "weather_packet.h"
#include "crc.h"

/*
 * Wire layout (little-endian, matches ARM native byte order):
 *   [0]     version     (1 byte)
 *   [1-2]   device_id   (2 bytes, LE)
 *   [3-6]   timestamp   (4 bytes, LE)
 *   [7]     temperature (1 byte, signed)
 *   [8]     humidity    (1 byte, unsigned)
 *   [9-10]  crc         (2 bytes, LE) — over bytes [0..8]
 */

#define CRC_DATA_LENGTH 9

void weather_packet_serialize(const WeatherPacket *pkt, uint8_t *buf)
{
    buf[0] = pkt->version;

    buf[1] = (uint8_t)(pkt->device_id & 0xFF);
    buf[2] = (uint8_t)(pkt->device_id >> 8);

    buf[3] = (uint8_t)(pkt->timestamp & 0xFF);
    buf[4] = (uint8_t)((pkt->timestamp >> 8)  & 0xFF);
    buf[5] = (uint8_t)((pkt->timestamp >> 16) & 0xFF);
    buf[6] = (uint8_t)((pkt->timestamp >> 24) & 0xFF);

    buf[7] = (uint8_t)pkt->temperature;
    buf[8] = pkt->humidity;

    uint16_t crc = crc16_ccitt(buf, CRC_DATA_LENGTH);
    buf[9]  = (uint8_t)(crc & 0xFF);
    buf[10] = (uint8_t)(crc >> 8);
}

bool weather_packet_deserialize(const uint8_t *buf, WeatherPacket *pkt)
{
    uint16_t expected = crc16_ccitt(buf, CRC_DATA_LENGTH);
    uint16_t actual   = (uint16_t)buf[9] | ((uint16_t)buf[10] << 8);
    if (expected != actual)
        return false;

    pkt->version     = buf[0];
    pkt->device_id   = (uint16_t)buf[1] | ((uint16_t)buf[2] << 8);
    pkt->timestamp   = (uint32_t)buf[3]
                     | ((uint32_t)buf[4] << 8)
                     | ((uint32_t)buf[5] << 16)
                     | ((uint32_t)buf[6] << 24);
    pkt->temperature = (int8_t)buf[7];
    pkt->humidity    = buf[8];
    pkt->crc         = actual;

    return true;
}

WeatherPacket weather_packet_create(uint16_t device_id, uint32_t timestamp,
                                    int8_t temperature, uint8_t humidity)
{
    WeatherPacket pkt;
    pkt.version     = WEATHER_PACKET_VERSION;
    pkt.device_id   = device_id;
    pkt.timestamp   = timestamp;
    pkt.temperature = temperature;
    pkt.humidity    = humidity;
    pkt.crc         = 0; /* filled by serialize */
    return pkt;
}
