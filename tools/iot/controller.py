"""
tools/iot/controller.py
Smart Home IoT Controller for JarvisX.

Integrates with Home Assistant REST API and direct MQTT.
Voice commands: "dim lights to 30%", "set thermostat to 22", "lock door"
"""
from __future__ import annotations
import re, threading, logging
from typing import Optional

log = logging.getLogger("iot_controller")


class IoTController:
    """
    Smart home IoT controller.
    Supports Home Assistant REST API and MQTT direct.
    """

    def __init__(
        self,
        ha_url: str = "",
        ha_token: str = "",
        mqtt_host: str = "",
        mqtt_port: int = 1883,
    ):
        self.ha_url   = (ha_url or "").rstrip("/")
        self.ha_token = ha_token
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.available = bool(ha_url or mqtt_host)
        self._mqtt_client = None
        if mqtt_host:
            self._init_mqtt()

    def _init_mqtt(self):
        try:
            import paho.mqtt.client as mqtt
            self._mqtt_client = mqtt.Client()
            self._mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self._mqtt_client.loop_start()
            log.info(f"IoTController: MQTT connected to {self.mqtt_host}")
        except Exception as e:
            log.warning(f"IoTController MQTT init failed: {e}")

    # ── Voice command parser ────────────────────────────────────────────────────

    def handle_command(self, text: str) -> Optional[str]:
        """
        Parse and execute IoT voice command.
        Returns response string or None if not an IoT command.
        """
        low = text.lower()

        # Lights
        m = re.search(r"(turn|switch)\s+(on|off)\s+(?:the\s+)?(.+?)\s+lights?", low)
        if m:
            state, room = m.group(2), m.group(3).strip()
            return self.control_light(room, state == "on")

        m = re.search(r"dim\s+(?:the\s+)?(.+?)\s+lights?\s+to\s+(\d+)", low)
        if m:
            room, pct = m.group(1).strip(), int(m.group(2))
            return self.set_light_brightness(room, pct)

        # Thermostat
        m = re.search(r"set\s+(?:the\s+)?thermostat\s+to\s+(\d+)", low)
        if m:
            return self.set_temperature(int(m.group(1)))

        # Locks
        if "lock" in low and ("door" in low or "front" in low or "home" in low):
            return self.lock_door()
        if "unlock" in low and ("door" in low or "front" in low):
            return self.unlock_door()

        # Fan / AC
        m = re.search(r"(turn|switch)\s+(on|off)\s+(?:the\s+)?(?:fan|ac|air\s*conditioning)", low)
        if m:
            return self.control_switch("fan", m.group(2) == "on")

        return None

    # ── Home Assistant API ──────────────────────────────────────────────────────

    def control_light(self, room: str, on: bool) -> str:
        service = "turn_on" if on else "turn_off"
        entity = f"light.{room.replace(' ', '_')}"
        result = self._ha_call("light", service, {"entity_id": entity})
        return result or f"{'Turning on' if on else 'Turning off'} {room} lights."

    def set_light_brightness(self, room: str, brightness_pct: int) -> str:
        entity = f"light.{room.replace(' ', '_')}"
        brightness = int(brightness_pct * 2.55)
        result = self._ha_call("light", "turn_on", {
            "entity_id": entity,
            "brightness": brightness,
        })
        return result or f"Setting {room} lights to {brightness_pct}%."

    def set_temperature(self, temp_celsius: int) -> str:
        result = self._ha_call("climate", "set_temperature", {
            "entity_id": "climate.thermostat",
            "temperature": temp_celsius,
        })
        return result or f"Thermostat set to {temp_celsius}°C."

    def lock_door(self) -> str:
        result = self._ha_call("lock", "lock", {"entity_id": "lock.front_door"})
        return result or "Front door locked."

    def unlock_door(self) -> str:
        result = self._ha_call("lock", "unlock", {"entity_id": "lock.front_door"})
        return result or "Front door unlocked."

    def control_switch(self, device: str, on: bool) -> str:
        service = "turn_on" if on else "turn_off"
        entity = f"switch.{device.replace(' ', '_')}"
        result = self._ha_call("switch", service, {"entity_id": entity})
        return result or f"{'Turning on' if on else 'Turning off'} {device}."

    def _ha_call(self, domain: str, service: str, data: dict) -> str:
        if not self.ha_url or not self.ha_token:
            return ""
        try:
            import requests
            url = f"{self.ha_url}/api/services/{domain}/{service}"
            headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}
            resp = requests.post(url, json=data, headers=headers, timeout=5)
            if resp.ok:
                log.info(f"IoT HA call OK: {domain}.{service}")
                return ""
            return f"Smart home error: {resp.status_code}"
        except Exception as e:
            log.warning(f"IoT HA call failed: {e}")
            return f"Smart home unreachable: {e}"

    # ── MQTT direct ────────────────────────────────────────────────────────────

    def mqtt_publish(self, topic: str, payload: str) -> str:
        if not self._mqtt_client:
            return "MQTT not connected."
        try:
            self._mqtt_client.publish(topic, payload)
            log.info(f"MQTT published: {topic} = {payload}")
            return f"Published to {topic}."
        except Exception as e:
            return f"MQTT publish failed: {e}"
