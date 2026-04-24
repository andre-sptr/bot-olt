package sheets

import (
	"encoding/csv"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"bges-bot/config"
)

// Struct to contain order's data
type OrderData struct {
	NoSC         string
	TanggalOrder string
	Durasi       string
	Status       string
	STO          string
	HSA          string
	District     string
}

// Mapping the sheets column
const (
	colNoSC         = 0
	colTanggalOrder = 1
	colStatus       = 12
	colSTO          = 18
	colDurasi       = 19
	colHSA          = 20
	colDistrict     = 21
	minColumns      = 22
)

// Fetching the data from google sheets
func FetchData(cfg config.Config) ([]OrderData, error) {
	csvURL := cfg.CSVExportURL()

	client := &http.Client{
		Timeout: 30 * time.Second,
	}

	resp, err := client.Get(csvURL)
	if err != nil {
		return nil, fmt.Errorf("gagal mengambil data dari Google Sheets: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Google Sheets mengembalikan status %d", resp.StatusCode)
	}

	return parseCSV(resp.Body)
}

// Parsing the csv data
func parseCSV(body io.Reader) ([]OrderData, error) {
	reader := csv.NewReader(body)
	reader.LazyQuotes = true
	reader.FieldsPerRecord = -1 // Allow variable number of fields

	records, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("failed to parse CSV: %w", err)
	}

	if len(records) < 2 {
		return nil, fmt.Errorf("data CSV kosong atau hanya berisi header")
	}

	var orders []OrderData

	// Skip the first row (header)
	for i := 1; i < len(records); i++ {
		row := records[i]

		// Skip rows with less columns than needed
		if len(row) < minColumns {
			continue
		}

		// Skip empty rows (check No. SC)
		noSC := strings.TrimSpace(row[colNoSC])
		if noSC == "" {
			continue
		}

		hsa := strings.TrimSpace(row[colHSA])
		if hsa == "" {
			continue
		}

		// Filter: only get dumai and pekanbaru
		district := strings.ToUpper(strings.TrimSpace(row[colDistrict]))
		if district != "DUMAI" && district != "PEKANBARU" {
			continue
		}

		tanggalOrder := formatTanggal(strings.TrimSpace(row[colTanggalOrder]))

		order := OrderData{
			NoSC:         noSC,
			TanggalOrder: tanggalOrder,
			Durasi:       strings.TrimSpace(row[colDurasi]),
			Status:       strings.TrimSpace(row[colStatus]),
			STO:          strings.TrimSpace(row[colSTO]),
			HSA:          hsa,
			District:     district,
		}

		orders = append(orders, order)
	}

	if len(orders) == 0 {
		return nil, fmt.Errorf("tidak ada data order yang valid ditemukan")
	}

	return orders, nil
}

// Formatting the date
func formatTanggal(raw string) string {
	if raw == "" {
		return "-"
	}

	layouts := []string{
		"2-Jan-06 15:04:05",
		"2-Jan-06 15:04",
		"2-Jan-06",
		"02-Jan-06 15:04:05",
		"02-Jan-06 15:04",
		"02-Jan-06",
		"1/2/2006 15:04:05",
		"1/2/2006",
	}

	for _, layout := range layouts {
		t, err := time.Parse(layout, raw)
		if err == nil {
			return t.Format("02/01/06")
		}
	}
	return raw
}
