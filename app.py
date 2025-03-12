import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
import keyboard

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants for Zwift Ride
RIDE_NAME = "Zwift Ride"  # Device name shown in logs
MANUFACTURER_ID = 2378  # Decimal representation of 0x094A
LEFT_DEVICE_ID = 8  # Device ID for Ride Left

CUSTOM_SERVICE_UUID = "0000fc82-0000-1000-8000-00805f9b34fb"
MEASUREMENT_CHAR_UUID = "00000002-19ca-4651-86e5-fa29dcdd09d1"
CONTROL_CHAR_UUID = "00000003-19ca-4651-86e5-fa29dcdd09d1"
RESPONSE_CHAR_UUID = "00000004-19ca-4651-86e5-fa29dcdd09d1"

# Button masks from the JavaScript code
BUTTON_MASKS = {
    "LEFT_BTN": 0x1,
    "UP_BTN": 0x2,
    "RIGHT_BTN": 0x4,
    "DOWN_BTN": 0x8,
    "A_BTN": 0x10,
    "B_BTN": 0x20,
    "Y_BTN": 0x40,
    "Z_BTN": 0x100,
    "SHFT_UP_L_BTN": 0x200,
    "SHFT_DN_L_BTN": 0x400,
    "POWERUP_L_BTN": 0x800,
    "ONOFF_L_BTN": 0x1000,
    "SHFT_UP_R_BTN": 0x2000,
    "SHFT_DN_R_BTN": 0x4000,
    "POWERUP_R_BTN": 0x10000,
    "ONOFF_R_BTN": 0x20000,
}

# Default key mapping - customize this as needed
DEFAULT_KEY_MAPPING = {
    "LEFT_BTN": "left",
    "UP_BTN": "up",
    "RIGHT_BTN": "right",
    "DOWN_BTN": "down",
    "A_BTN": "a",
    "B_BTN": "b",
    "Y_BTN": "y",
    "Z_BTN": "z",
    "SHFT_UP_L_BTN": "w",
    "SHFT_DN_L_BTN": "s",
    "POWERUP_L_BTN": "space",
    "ONOFF_L_BTN": "escape",
    "SHFT_UP_R_BTN": "page up",
    "SHFT_DN_R_BTN": "page down",
    "POWERUP_R_BTN": "p",
    "ONOFF_R_BTN": "enter"
}


class ZwiftRideController:
    def __init__(self, key_mapping=None):
        self.device: Optional[BLEDevice] = None
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.key_mapping = key_mapping or DEFAULT_KEY_MAPPING
        self.pressed_buttons = set()
        # Track last press time to handle repeated presses
        self.last_press_time = {}
        # Minimum time between repeated keypresses (in seconds)
        self.repeat_delay = 0.2
        # Keep track of which keys are currently being held down
        self.active_keys = set()
        # Store discovered devices for selection
        self.discovered_devices = []

    def load_key_mapping(self, json_file: str) -> None:
        """Load key mapping from a JSON file"""
        try:
            with open(json_file, 'r') as f:
                self.key_mapping = json.load(f)
            logger.info(f"Loaded key mapping from {json_file}")
        except Exception as e:
            logger.error(f"Error loading key mapping: {e}")

    def save_key_mapping(self, json_file: str) -> None:
        """Save current key mapping to a JSON file"""
        try:
            with open(json_file, 'w') as f:
                json.dump(self.key_mapping, f, indent=4)
            logger.info(f"Saved key mapping to {json_file}")
        except Exception as e:
            logger.error(f"Error saving key mapping: {e}")

    def is_left_controller(self, device: BLEDevice, adv_data: AdvertisementData) -> bool:
        """Check if device is the left Zwift Ride controller based on manufacturer data"""
        if not device.name or RIDE_NAME not in device.name:
            return False

        # Check if manufacturer data exists
        if not hasattr(adv_data, 'manufacturer_data') or not adv_data.manufacturer_data:
            return False

        # Based on your logs, we're looking for manufacturer ID 2378 and device ID 8 in the first byte
        manuf_data = adv_data.manufacturer_data.get(MANUFACTURER_ID)
        if manuf_data is not None and len(manuf_data) >= 1:
            device_id = manuf_data[0]
            logger.info(f"Device {device.name} [{device.address}] has device ID: {device_id}")
            return device_id == LEFT_DEVICE_ID

        return False

    async def scan_for_device(self) -> bool:
        """Scan for Zwift Ride left controller only"""
        logger.info(f"Scanning for Zwift Ride left controller (device_id {LEFT_DEVICE_ID})...")
        self.discovered_devices = []
        left_controller_found = False

        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            nonlocal left_controller_found

            # First just log all Zwift devices for debugging
            if device.name and RIDE_NAME in device.name:
                logger.info(f"Found device: {device.name} [{device.address}]")
                logger.info(f"  RSSI: {advertisement_data.rssi if hasattr(advertisement_data, 'rssi') else 'Unknown'}")

                # Print manufacturer data for debugging
                if hasattr(advertisement_data, 'manufacturer_data'):
                    logger.info(f"  Manufacturer data: {advertisement_data.manufacturer_data}")

                # Check if it's the left controller
                if self.is_left_controller(device, advertisement_data):
                    logger.info(f"*** IDENTIFIED as LEFT controller! ***")
                    # Store the left controller
                    if device not in self.discovered_devices:
                        self.discovered_devices.append(device)
                        left_controller_found = True

        # Scan for devices
        scanner = BleakScanner()
        scanner.register_detection_callback(detection_callback)
        await scanner.start()

        # Scan until we find the left controller or timeout
        scan_time = 0
        max_scan_time = 30  # Maximum scan time in seconds
        while not left_controller_found and scan_time < max_scan_time:
            await asyncio.sleep(1.0)
            scan_time += 1
            logger.info(f"Scanning... {scan_time}/{max_scan_time} seconds")

        await scanner.stop()

        if not self.discovered_devices:
            logger.error(f"No Zwift Ride left controller (device_id {LEFT_DEVICE_ID}) found")
            return False

        # Use the first left controller we found
        self.device = self.discovered_devices[0]
        logger.info(f"Selected left controller: {self.device.name} [{self.device.address}]")
        return True

    async def connect(self) -> bool:
        """Connect to the Zwift Ride left controller"""
        if not self.device:
            logger.error("No left controller to connect to. Please scan first.")
            return False

        logger.info(f"Connecting to left controller {self.device.name} [{self.device.address}]...")

        try:
            self.client = BleakClient(self.device)
            await self.client.connect()
            logger.info("Connected to left controller")

            # Perform initial handshake
            control_char = self.client.services.get_characteristic(CONTROL_CHAR_UUID)
            await self.client.write_gatt_char(control_char, b"RideOn")
            logger.info("Sent RideOn handshake")

            # Set up notifications for measurement characteristic
            measurement_char = self.client.services.get_characteristic(MEASUREMENT_CHAR_UUID)
            await self.client.start_notify(measurement_char, self.notification_handler)

            # Set up notifications for response characteristic
            response_char = self.client.services.get_characteristic(RESPONSE_CHAR_UUID)
            await self.client.start_notify(response_char, self.response_handler)

            self.connected = True
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.client and self.connected:
            # Release all keys that might still be pressed
            for key in self.active_keys:
                keyboard.release(key)
            self.active_keys.clear()

            await self.client.disconnect()
            logger.info("Disconnected from device")
            self.connected = False

    def response_handler(self, _: int, data: bytearray) -> None:
        """Handle responses from the device"""
        try:
            response = data.decode('utf-8')
            logger.info(f"Response: {response}")
        except Exception as e:
            logger.error(f"Error decoding response: {e}")

    def notification_handler(self, _: int, data: bytearray) -> None:
        """Handle incoming notifications from the device"""
        try:
            msg_type = data[0]

            if msg_type == 0x23:  # Button status
                button_map = data[2] | (data[3] << 8) | (data[4] << 16) | (data[5] << 24)
                pressed_buttons = self.parse_button_state(button_map)

                if pressed_buttons:
                    logger.info(f"Buttons pressed: {', '.join(pressed_buttons)}")
                    self.trigger_keystrokes(pressed_buttons)

                # Process analog values if present
                start_index = 7
                while start_index < len(data):
                    analog_data = self.parse_analog_message(data[start_index:])
                    if not analog_data:
                        break

                    #logger.info(f"Analog left:{analog_data['left']} right:{analog_data['right']}")
                    start_index = analog_data.get('next_index', len(data))

            elif msg_type == 0x2a:  # Initial status
                logger.info("Initial status received")

            elif msg_type == 0x15:  # Idle
                # On idle, make sure all keys are released
                if self.active_keys:
                    for key in list(self.active_keys):
                        keyboard.release(key)
                    self.active_keys.clear()
                    self.pressed_buttons.clear()

            elif msg_type == 0x19:  # Status update
                pass  # Ignore regular status updates

            else:
                hex_data = ' '.join([f"{b:02x}" for b in data])
                logger.debug(f"Unknown message: {hex_data}")

        except Exception as e:
            logger.error(f"Error processing notification: {e}")

    def parse_button_state(self, button_map: int) -> List[str]:
        """Parse button state from button map"""
        pressed_buttons = []
        for button, mask in BUTTON_MASKS.items():
            # Note: 0 means pressed in the protocol (like JavaScript version)
            if (button_map & mask) == 0:
                pressed_buttons.append(button)
        return pressed_buttons

    def parse_key_press(self, buffer: bytearray) -> Dict[str, Any]:
        """Parse a key press from protobuf format"""
        location = None
        analog_value = None
        offset = 0

        while offset < len(buffer):
            tag = buffer[offset]
            field_num = tag >> 3
            wire_type = tag & 0x7
            offset += 1

            if field_num == 1 and wire_type == 0:  # Location
                value = 0
                shift = 0
                while True:
                    byte = buffer[offset]
                    offset += 1
                    value |= (byte & 0x7f) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                location = value

            elif field_num == 2 and wire_type == 0:  # AnalogValue
                value = 0
                shift = 0
                while True:
                    byte = buffer[offset]
                    offset += 1
                    value |= (byte & 0x7f) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7
                # ZigZag decode for sint32
                analog_value = (value >> 1) ^ (-(value & 1))

            else:
                # Skip unknown fields
                if wire_type == 0:  # Varint
                    while buffer[offset] & 0x80:
                        offset += 1
                    offset += 1
                elif wire_type == 2:  # Length-delimited
                    length = buffer[offset]
                    offset += 1 + length

        return {"location": location, "value": analog_value}

    def parse_key_group(self, buffer: bytearray) -> Dict[int, int]:
        """Parse a group of key presses"""
        group_status = {}
        offset = 0

        while offset < len(buffer):
            tag = buffer[offset]
            field_num = tag >> 3
            wire_type = tag & 0x7
            offset += 1

            if field_num == 3 and wire_type == 2:  # KeyPress message
                length = buffer[offset]
                offset += 1
                message_buffer = buffer[offset:offset + length]
                res = self.parse_key_press(message_buffer)

                if res["location"] is not None:
                    group_status[res["location"]] = res["value"]

                offset += length

            else:
                # Skip unknown fields
                if wire_type == 0:  # Varint
                    while offset < len(buffer) and buffer[offset] & 0x80:
                        offset += 1
                    if offset < len(buffer):
                        offset += 1
                elif wire_type == 2:  # Length-delimited
                    if offset < len(buffer):
                        length = buffer[offset]
                        offset += 1 + length

        return group_status

    def parse_analog_message(self, data: bytearray) -> Optional[Dict[str, Any]]:
        """Parse an analog message"""
        if not data or data[0] != 0x1a:
            return None

        res = self.parse_key_group(data)
        return {
            "left": res.get(0, 0),
            "right": res.get(1, 0),
            "next_index": len(data)  # We'd need to calculate actual next index in a more complex case
        }

    def trigger_keystrokes(self, buttons: List[str]) -> None:
        """Trigger keystrokes based on button presses"""
        current_time = time.time()
        current_buttons = set(buttons)

        # For buttons that were pressed before and still pressed:
        # We need to handle possible repeats
        for button in current_buttons & self.pressed_buttons:
            if button in self.key_mapping:
                last_time = self.last_press_time.get(button, 0)
                # Check if enough time has passed for a repeat
                if current_time - last_time >= self.repeat_delay:
                    key = self.key_mapping[button]

                    # For repeat presses, we need to release and press again to simulate repeated keypresses
                    logger.info(f"Repeat press: {key}")
                    if key in self.active_keys:
                        keyboard.release(key)
                        self.active_keys.remove(key)

                    # Small delay between release and press for repeat keys
                    time.sleep(0.01)
                    keyboard.press(key)
                    self.active_keys.add(key)
                    self.last_press_time[button] = current_time

        # For buttons that are newly pressed:
        # These are buttons in current_buttons but not in self.pressed_buttons
        for button in current_buttons - self.pressed_buttons:
            if button in self.key_mapping:
                key = self.key_mapping[button]
                logger.info(f"New press: {key}")
                keyboard.press(key)
                self.active_keys.add(key)
                self.last_press_time[button] = current_time

        # For buttons that are released:
        # These are buttons in self.pressed_buttons but not in current_buttons
        for button in self.pressed_buttons - current_buttons:
            if button in self.key_mapping:
                key = self.key_mapping[button]
                logger.info(f"Releasing: {key}")
                keyboard.release(key)
                if key in self.active_keys:
                    self.active_keys.remove(key)

        # Update the pressed buttons state
        self.pressed_buttons = current_buttons


async def main():
    """Main function to run the controller"""
    controller = ZwiftRideController()

    # Optionally load custom key mapping from a file
    try:
        controller.load_key_mapping("key_mapping.json")
    except:
        logger.info("Using default key mapping")

    try:
        # Keep attempting to connect if needed
        connected = False
        max_attempts = 3
        attempts = 0

        while not connected and attempts < max_attempts:
            attempts += 1
            logger.info(f"Connection attempt {attempts}/{max_attempts}")

            if await controller.scan_for_device():
                if await controller.connect():
                    connected = True
                    logger.info("Connected to left controller and listening for input. Press Ctrl+C to exit.")

                    try:
                        # Keep the program running
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        logger.info("Interrupted by user")
                    finally:
                        await controller.disconnect()

            if not connected and attempts < max_attempts:
                logger.info(f"Failed to connect. Retrying in 5 seconds...")
                await asyncio.sleep(5)

        if not connected:
            logger.error(f"Failed to connect after {max_attempts} attempts.")

    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    # Save the default mapping as an example
    #with open("key_mapping.json", "w") as f:
    #    json.dump(DEFAULT_KEY_MAPPING, f, indent=4)

    print("Starting Zwift Ride Controller (automatically connecting to LEFT controller)...")
    print("Default key mapping saved to key_mapping.json")
    print("Press Ctrl+C to exit")

    asyncio.run(main())