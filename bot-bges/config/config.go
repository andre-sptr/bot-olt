package config

import "fmt"

// Config to save waha api and google sheets configuration
type Config struct {
	WahaURL       string
	WahaSession   string
	WahaAPIKey    string
	SpreadsheetID string
	SheetGID      string
	GroupID       string
}

// Default config
func DefaultConfig() Config {
	return Config{
		WahaURL:     "https://waha-dutxvo095iqn.cgk-lab.sumopod.my.id",
		WahaSession: "OLTReport",
		WahaAPIKey:  "ROpWNPkTUavqEbnz5zKU4mTiL0HIZoye",

		SpreadsheetID: "1AYoyWx5Dw_ewK0HhFgxJJ0wJF20sgBxkAmwhqHGAI98",
		SheetGID:      "1401050607",

		GroupID: "120363423984319917@g.us",
	}
}

// Export the url
func (c Config) CSVExportURL() string {
	return fmt.Sprintf(
		"https://docs.google.com/spreadsheets/d/%s/export?format=csv&gid=%s",
		c.SpreadsheetID,
		c.SheetGID,
	)
}
