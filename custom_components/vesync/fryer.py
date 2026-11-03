"""Controls for dual-basket air fryers (Cosori Turbo Tower Pro, Dual Blaze).

The appliance is programmed in two steps: the program, temperature and time chosen
here are kept per basket in Home Assistant, and a button sends them to the fryer
(``prepare``). The fryer still needs its physical Start button pressed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
import logging
from typing import override

from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.const import (
    DC111_PROGRAM_LIMITS_C,
    DC111_PROGRAM_LIMITS_F,
    DC111_TEMPERATURE_STEP_C,
)
from pyvesync.devices.vesynckitchen import DC111_SYNC_FINISH, DC111_SYNC_MATCH

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.components.select import SelectEntity
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.exceptions import HomeAssistantError

from .common import is_dual_air_fryer
from .coordinator import VeSyncDataCoordinator
from .entity import VeSyncBaseEntity

_LOGGER = logging.getLogger(__name__)

DEFAULT_MODE = "AirFry"
DEFAULT_TEMPERATURE = {"celsius": 180, "fahrenheit": 360}
DEFAULT_MINUTES = 10
BASKETS = (1, 2)


@dataclass
class BasketPlan:
    """What to send to one basket on the next prepare."""

    mode: str = DEFAULT_MODE
    temperature: int | None = None
    minutes: int = DEFAULT_MINUTES


def get_plan(
    coordinator: VeSyncDataCoordinator, device: VeSyncBaseDevice, basket: int
) -> BasketPlan:
    """Return the plan for a basket, creating it on first use."""
    plans = coordinator.__dict__.setdefault("fryer_plans", {})
    return plans.setdefault(device.cid, {n: BasketPlan() for n in BASKETS})[basket]


def limits(
    device: VeSyncBaseDevice, mode: str
) -> tuple[int, int, int, int, int, int]:
    """Return (min temp, max temp, temp step, min minutes, max minutes, minute step)."""
    min_c, max_c, min_m, max_m, m_step = DC111_PROGRAM_LIMITS_C[mode]
    if device.temp_unit == "fahrenheit":
        min_t, max_t, t_step = DC111_PROGRAM_LIMITS_F[mode]
    else:
        min_t, max_t, t_step = min_c, max_c, DC111_TEMPERATURE_STEP_C
    return min_t, max_t, t_step, min_m, max_m, m_step


def _snap(value: float, low: int, high: int, step: int) -> int:
    """Clamp a value into a range and snap it to the step from the range start."""
    value = min(max(value, low), high)
    return min(low + round((value - low) / step) * step, high)


def plan_config(
    device: VeSyncBaseDevice, plan: BasketPlan
) -> dict[str, int | str]:
    """Return the plan as a valid prepare request for the current unit and mode."""
    min_t, max_t, t_step, min_m, max_m, m_step = limits(device, plan.mode)
    temperature = plan.temperature or DEFAULT_TEMPERATURE.get(device.temp_unit, 180)
    return {
        "mode": plan.mode,
        "temperature": _snap(temperature, min_t, max_t, t_step),
        "minutes": _snap(plan.minutes, min_m, max_m, m_step),
    }


def modes(device: VeSyncBaseDevice) -> list[str]:
    """Return the programs this model offers."""
    if device.device_type.startswith("CAF-DC111"):
        return list(device.cook_modes)
    # The Dual Blaze has neither the Dry nor the Proof program.
    return [mode for mode in device.cook_modes if mode not in ("Dry", "Proof")]


class FryerEntity(VeSyncBaseEntity):
    """Base for the dual-basket air fryer control entities."""

    def __init__(
        self,
        device: VeSyncBaseDevice,
        coordinator: VeSyncDataCoordinator,
        key: str,
        name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(device, coordinator)
        self._attr_unique_id = f"{super().unique_id}-{key}"
        self._attr_name = name


class FryerProgramSelect(FryerEntity, SelectEntity):
    """Program (cooking mode) for the next prepare of a basket."""

    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, device, coordinator, basket: int) -> None:
        """Initialize the select."""
        super().__init__(
            device,
            coordinator,
            f"basket_{basket}_program_select",
            f"Basket {basket} program selection",
        )
        self._basket = basket
        self._attr_options = modes(device)

    @property
    @override
    def current_option(self) -> str:
        """Return the chosen program."""
        return get_plan(self.coordinator, self.device, self._basket).mode

    @override
    async def async_select_option(self, option: str) -> None:
        """Choose a program."""
        get_plan(self.coordinator, self.device, self._basket).mode = option
        self.coordinator.async_update_listeners()


class FryerTemperatureNumber(FryerEntity, NumberEntity):
    """Temperature for the next prepare of a basket."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX

    def __init__(self, device, coordinator, basket: int) -> None:
        """Initialize the number."""
        super().__init__(
            device,
            coordinator,
            f"basket_{basket}_temperature_select",
            f"Basket {basket} temperature selection",
        )
        self._basket = basket

    def _plan(self) -> BasketPlan:
        return get_plan(self.coordinator, self.device, self._basket)

    @property
    @override
    def native_value(self) -> float:
        """Return the chosen temperature."""
        return plan_config(self.device, self._plan())["temperature"]

    @property
    @override
    def native_min_value(self) -> float:
        """Return the lowest temperature for the chosen program."""
        return limits(self.device, self._plan().mode)[0]

    @property
    @override
    def native_max_value(self) -> float:
        """Return the highest temperature for the chosen program."""
        return limits(self.device, self._plan().mode)[1]

    @property
    @override
    def native_step(self) -> float:
        """Return the temperature step for the chosen program."""
        return limits(self.device, self._plan().mode)[2]

    @property
    @override
    def native_unit_of_measurement(self) -> str:
        """Return the unit the fryer is set to."""
        if self.device.temp_unit == "fahrenheit":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Choose a temperature."""
        self._plan().temperature = int(value)
        self.coordinator.async_update_listeners()


class FryerTimeNumber(FryerEntity, NumberEntity):
    """Cooking time for the next prepare of a basket."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, device, coordinator, basket: int) -> None:
        """Initialize the number."""
        super().__init__(
            device,
            coordinator,
            f"basket_{basket}_time_select",
            f"Basket {basket} time selection",
        )
        self._basket = basket

    def _plan(self) -> BasketPlan:
        return get_plan(self.coordinator, self.device, self._basket)

    @property
    @override
    def native_value(self) -> float:
        """Return the chosen time."""
        return plan_config(self.device, self._plan())["minutes"]

    @property
    @override
    def native_min_value(self) -> float:
        """Return the shortest time for the chosen program."""
        return limits(self.device, self._plan().mode)[3]

    @property
    @override
    def native_max_value(self) -> float:
        """Return the longest time for the chosen program."""
        return limits(self.device, self._plan().mode)[4]

    @property
    @override
    def native_step(self) -> float:
        """Return the time step for the chosen program."""
        return limits(self.device, self._plan().mode)[5]

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Choose a time."""
        self._plan().minutes = int(value)
        self.coordinator.async_update_listeners()


type PressFn = Callable[[VeSyncDataCoordinator, VeSyncBaseDevice], Awaitable[bool]]


def _prepare(basket: int) -> PressFn:
    async def press(coordinator, device) -> bool:
        cfg = plan_config(device, get_plan(coordinator, device, basket))
        # The fryer refuses a new program on a basket that already has one.
        await device.stop_chamber(basket)
        return await device.prepare_program(
            basket, cfg["temperature"], cfg["minutes"], cfg["mode"]
        )

    return press


def _prepare_both(sync_type: int) -> PressFn:
    async def press(coordinator, device) -> bool:
        cfgs = [
            plan_config(device, get_plan(coordinator, device, basket))
            for basket in BASKETS
        ]
        for basket in BASKETS:
            await device.stop_chamber(basket)
        return await device.prepare_both_chambers(cfgs[0], cfgs[1], sync_type)

    return press


def _stop(*baskets: int) -> PressFn:
    async def press(coordinator, device) -> bool:
        # A basket with nothing to stop is not an error.
        for basket in baskets:
            await device.stop_chamber(basket)
        return True

    return press


async def _refresh(coordinator: VeSyncDataCoordinator, device) -> bool:
    return True


BUTTONS: tuple[tuple[str, str, str, PressFn], ...] = (
    ("prepare_both_same", "Prepare both baskets the same", "mdi:chef-hat",
     _prepare_both(DC111_SYNC_MATCH)),
    ("stop_both", "Stop both baskets", "mdi:stop-circle-outline", _stop(1, 2)),
    ("prepare_both_sync", "Prepare both baskets to finish together", "mdi:chef-hat",
     _prepare_both(DC111_SYNC_FINISH)),
    ("refresh", "Refresh now", "mdi:refresh", _refresh),
    ("stop_basket_1", "Basket 1 stop program", "mdi:stop-circle-outline", _stop(1)),
    ("prepare_basket_1", "Basket 1 prepare program", "mdi:chef-hat", _prepare(1)),
    ("stop_basket_2", "Basket 2 stop program", "mdi:stop-circle-outline", _stop(2)),
    ("prepare_basket_2", "Basket 2 prepare program", "mdi:chef-hat", _prepare(2)),
)


class FryerButton(FryerEntity, ButtonEntity):
    """A button that sends a command to the fryer."""

    def __init__(self, device, coordinator, key, name, icon, press: PressFn) -> None:
        """Initialize the button."""
        super().__init__(device, coordinator, key, name)
        self._attr_icon = icon
        self._press = press

    @override
    async def async_press(self) -> None:
        """Send the command, then refresh the state."""
        try:
            accepted = await self._press(self.coordinator, self.device)
        except (ValueError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err
        if not accepted:
            raise HomeAssistantError(f"{self.name}: the air fryer did not accept it")
        await self.coordinator.async_request_refresh()


def fryer_buttons(
    devices: Iterable[VeSyncBaseDevice], coordinator: VeSyncDataCoordinator
) -> list[FryerButton]:
    """Return the buttons for every dual-basket air fryer."""
    return [
        FryerButton(dev, coordinator, key, name, icon, press)
        for dev in devices
        if is_dual_air_fryer(dev)
        for key, name, icon, press in BUTTONS
    ]


def fryer_selects(
    devices: Iterable[VeSyncBaseDevice], coordinator: VeSyncDataCoordinator
) -> list[FryerProgramSelect]:
    """Return the program selects for every dual-basket air fryer."""
    return [
        FryerProgramSelect(dev, coordinator, basket)
        for dev in devices
        if is_dual_air_fryer(dev)
        for basket in BASKETS
    ]


def fryer_numbers(
    devices: Iterable[VeSyncBaseDevice], coordinator: VeSyncDataCoordinator
) -> list[NumberEntity]:
    """Return the temperature and time numbers for every dual-basket air fryer."""
    return [
        entity(dev, coordinator, basket)
        for dev in devices
        if is_dual_air_fryer(dev)
        for basket in BASKETS
        for entity in (FryerTemperatureNumber, FryerTimeNumber)
    ]
