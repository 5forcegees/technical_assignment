#include "mqtt_client.h"
#include <stdio.h>

/*
 * Mock MQTT client for host-side testing.
 * Prints hex payload to stdout instead of transmitting.
 */

int mqtt_connect(const char *broker_host, uint16_t port, const char *client_id)
{
    printf("[MQTT] connect  host=%s port=%u client=%s\n",
           broker_host, port, client_id);
    return 0;
}

int mqtt_publish(const char *topic, const uint8_t *payload, size_t len)
{
    printf("[MQTT] publish  topic=%s  payload=", topic);
    for (size_t i = 0; i < len; i++)
        printf("%02X", payload[i]);
    printf("  (%zu bytes)\n", len);
    return 0;
}

void mqtt_disconnect(void)
{
    printf("[MQTT] disconnect\n");
}
