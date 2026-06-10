#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <stdint.h>
#include <stddef.h>

/*
 * MQTT client HAL.
 *
 * On real hardware this wraps the radio driver + TLS stack.
 * The mock implementation prints payloads to stdout for testing.
 */

/* Connect to broker. Returns 0 on success, -1 on failure. */
int mqtt_connect(const char *broker_host, uint16_t port, const char *client_id);

/* Publish binary payload to topic. Returns 0 on success, -1 on failure. */
int mqtt_publish(const char *topic, const uint8_t *payload, size_t len);

void mqtt_disconnect(void);

#endif /* MQTT_CLIENT_H */
