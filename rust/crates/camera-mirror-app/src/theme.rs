//! Dark and light visual themes matching the desktop app palette.

use eframe::egui::{self, Color32, Stroke};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn from_preference(value: &str) -> Self {
        if value == "light" {
            Self::Light
        } else {
            Self::Dark
        }
    }

    pub fn as_preference(self) -> &'static str {
        match self {
            Self::Dark => "dark",
            Self::Light => "light",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Dark => "Gelap",
            Self::Light => "Terang",
        }
    }

    pub fn apply(self, context: &egui::Context) {
        let mut visuals = match self {
            Self::Dark => egui::Visuals::dark(),
            Self::Light => egui::Visuals::light(),
        };
        let accent = if self == Self::Dark {
            Color32::from_rgb(0xa1, 0x4b, 0x45)
        } else {
            Color32::from_rgb(0x93, 0x41, 0x3b)
        };
        visuals.selection.bg_fill = accent;
        visuals.selection.stroke = Stroke::new(1.0, Color32::WHITE);
        visuals.hyperlink_color = accent;
        visuals.widgets.active.bg_fill = accent;
        visuals.widgets.hovered.bg_fill = if self == Self::Dark {
            Color32::from_rgb(0x3a, 0x3a, 0x37)
        } else {
            Color32::from_rgb(0xdd, 0xdc, 0xd6)
        };
        context.set_theme(match self {
            Self::Dark => egui::ThemePreference::Dark,
            Self::Light => egui::ThemePreference::Light,
        });
        context.set_visuals(visuals);
        context.all_styles_mut(|style| {
            style.spacing.item_spacing = egui::vec2(8.0, 8.0);
            style.spacing.button_padding = egui::vec2(10.0, 6.0);
        });
    }
}
