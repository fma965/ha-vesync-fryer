"""Support for VeSync buttons."""

from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.device_container import DeviceContainer

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import VS_DEVICES, VS_DISCOVERY
from .coordinator import VesyncConfigEntry, VeSyncDataCoordinator
from .fryer import fryer_buttons

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VesyncConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities."""

    coordinator = config_entry.runtime_data

    @callback
    def discover(devices: list[VeSyncBaseDevice]) -> None:
        """Add new devices to platform."""
        _setup_entities(devices, async_add_entities, coordinator)

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, VS_DISCOVERY.format(VS_DEVICES), discover)
    )

    _setup_entities(
        config_entry.runtime_data.manager.devices, async_add_entities, coordinator
    )


@callback
def _setup_entities(
    devices: DeviceContainer | list[VeSyncBaseDevice],
    async_add_entities: AddConfigEntryEntitiesCallback,
    coordinator: VeSyncDataCoordinator,
) -> None:
    """Add button entities."""
    async_add_entities(fryer_buttons(devices, coordinator))
