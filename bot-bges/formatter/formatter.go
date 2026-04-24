package formatter

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"bges-bot/sheets"
)

// Grouping the hsa data
type HSAGroup struct {
	HSA      string
	District string
	Orders   []sheets.OrderData
}

// Group the orders data by HSA and return the slice
func GroupByHSA(data []sheets.OrderData) []HSAGroup {
	// Map to group the orders data by HSA
	groupMap := make(map[string]*HSAGroup)

	for _, order := range data {
		key := order.HSA
		if group, exists := groupMap[key]; exists {
			group.Orders = append(group.Orders, order)
		} else {
			groupMap[key] = &HSAGroup{
				HSA:      order.HSA,
				District: order.District,
				Orders:   []sheets.OrderData{order},
			}
		}
	}

	// Convert map to slice and sort by HSA
	groups := make([]HSAGroup, 0, len(groupMap))
	for _, group := range groupMap {
		groups = append(groups, *group)
	}

	sort.Slice(groups, func(i, j int) bool {
		return groups[i].HSA < groups[j].HSA
	})

	return groups
}

// Creating the main header for the report
func FormatHeader() string {
	waktu := time.Now().Format("02/01/06 15:04")

	return fmt.Sprintf(
		"📊 *REPORT SEND SURVEY & PI INDIBIZ*\n"+
			"\n"+
			"Dibuat oleh BGES.SBT\n"+
			"Tanggal: %s", waktu,
	)
}

// Formatting the hsa message
func FormatHSAMessage(group HSAGroup) string {
	var sb strings.Builder

	// Header HSA
	sb.WriteString(fmt.Sprintf("*HSA %s - DISTRICT %s*\n", group.HSA, group.District))

	// Header column
	sb.WriteString("*No. SC - Tgl Order - Durasi - Status - STO*\n")

	// Data rows
	for _, order := range group.Orders {
		sb.WriteString(fmt.Sprintf(
			"%s - %s - %s - %s - %s\n",
			order.NoSC,
			order.TanggalOrder,
			order.Durasi,
			order.Status,
			order.STO,
		))
	}

	sb.WriteString(fmt.Sprintf("_Total: %d order_", len(group.Orders)))

	return sb.String()
}

// Formatting the whole message to be sent for 1 message
func FormatMessage(data []sheets.OrderData) string {
	groups := GroupByHSA(data)

	var sb strings.Builder

	// Header report
	sb.WriteString(FormatHeader())
	sb.WriteString(fmt.Sprintf("\nTotal: %d Order\n", len(data)))

	// All HSA in one message
	for _, group := range groups {
		sb.WriteString("\n")
		sb.WriteString(FormatHSAMessage(group))
		sb.WriteString("\n")
	}

	return sb.String()
}
