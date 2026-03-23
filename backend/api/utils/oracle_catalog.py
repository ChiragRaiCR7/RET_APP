"""
Oracle E-Business Suite / Fusion module catalog.

Backend-canonical authority for Oracle module metadata.
All groups detected during ZIP scanning are enriched through this module.
"""

from __future__ import annotations
from typing import Optional, TypedDict


class OracleModuleInfo(TypedDict):
    name: str
    domain: str
    is_obsolete: bool


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------
DOMAIN_FINANCE = "Finance & Accounting"
DOMAIN_SUPPLY_CHAIN = "Supply Chain"
DOMAIN_MANUFACTURING = "Manufacturing"
DOMAIN_ORDER_MGMT = "Order Management"
DOMAIN_HR = "Human Resources"
DOMAIN_CRM = "CRM & Sales"
DOMAIN_PROJECTS = "Projects"
DOMAIN_ANALYTICS = "Intelligence & Analytics"
DOMAIN_COMMS = "Communications & Telecom"
DOMAIN_PUBLIC_SECTOR = "Public Sector"
DOMAIN_PLATFORM = "Platform & Technology"

# ---------------------------------------------------------------------------
# Full Oracle EBS module catalog
# code (uppercase) -> OracleModuleInfo
# ---------------------------------------------------------------------------
_CATALOG: dict[str, OracleModuleInfo] = {
    # ---- Platform & Technology ----
    "FND":       {"name": "Application Object Library",                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "SYSADMIN":  {"name": "System Administration",                         "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AU":        {"name": "Application Utilities",                         "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AD":        {"name": "Applications DBA",                              "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ALR":       {"name": "Alert",                                         "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "RG":        {"name": "Application Report Generator",                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AK":        {"name": "Common Modules-AK",                             "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AZ":        {"name": "Application Implementation",                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "SHT":       {"name": "Applications Shared Technology",                "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ECX":       {"name": "XML Gateway",                                   "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "EC":        {"name": "e-Commerce Gateway",                            "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "FRM":       {"name": "Report Manager",                                "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "MWA":       {"name": "Mobile Applications",                           "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ICX":       {"name": "Oracle iProcurement",                           "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "XDO":       {"name": "XML Publisher",                                 "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "OAM":       {"name": "Oracle Applications Manager",                   "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "BNE":       {"name": "Web Applications Desktop Integrator",           "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AME":       {"name": "Approvals Management",                          "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "IZU":       {"name": "Oracle E-Business Suite Diagnostics",           "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "PTX":       {"name": "Patch Tracking System",                         "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "EMS":       {"name": "Environment Management System",                 "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JMF":       {"name": "Supply Chain Localizations",                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JA":        {"name": "Asia/Pacific Localizations",                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JE":        {"name": "European Localizations",                        "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JG":        {"name": "Regional Localizations",                        "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JL":        {"name": "Latin America Localizations",                   "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JTS":       {"name": "CRM Self Service Administration",               "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "JTM":       {"name": "Mobile Application Foundation",                 "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ITG":       {"name": "Internet Procurement Enterprise Connector",     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "AMW":       {"name": "Internal Controls Manager",                     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ADS":       {"name": "Applications Demonstration Services",           "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ADS_DEV":   {"name": "ADS Development",                              "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CUSTOM":    {"name": "Custom Development",                            "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "DNA":       {"name": "Development",                                   "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "TEST":      {"name": "Test",                                          "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "WMA":       {"name": "Manufacturing Mobile Applications",             "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "MIA":       {"name": "Mobile Applications for Inventory Management",  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "MQA":       {"name": "Mobile Quality Applications",                   "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "IPM":       {"name": "Oracle Imaging Process Management",             "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "XLE":       {"name": "Legal Entity Configurator",                     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "FUN":       {"name": "Financials Common Modules",                     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "EDR":       {"name": "E-Records",                                     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CLN":       {"name": "Supply Chain Trading Connector for RosettaNet", "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "DOM":       {"name": "Document Management and Collaboration",         "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "IBC":       {"name": "Content Manager",                               "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "DEM":       {"name": "Demo Order Entry (AOL Class)",                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},

    # ---- Finance & Accounting ----
    "SQLGL":     {"name": "General Ledger",                                "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "SQLAP":     {"name": "Payables",                                      "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "AR":        {"name": "Receivables",                                   "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "OFA":       {"name": "Assets",                                        "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "CE":        {"name": "Cash Management",                               "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "XLA":       {"name": "Subledger Accounting",                          "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "XTR":       {"name": "Treasury",                                      "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "IBY":       {"name": "Payments",                                      "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "IBP":       {"name": "Bill Presentment & Payment",                    "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "AX":        {"name": "Global Accounting Engine",                      "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "GCS":       {"name": "Financial Consolidation Hub",                   "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "LNS":       {"name": "Loans",                                         "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "ZX":        {"name": "E-Business Tax",                                "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "PN":        {"name": "Property Manager",                              "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "IA":        {"name": "iAssets",                                       "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "GMF":       {"name": "Process Manufacturing Financials",              "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "FEM":       {"name": "Enterprise Performance Foundation",             "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "PFT":       {"name": "Oracle Profitability Manager",                  "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "FTP":       {"name": "Transfer Pricing",                              "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "RMG":       {"name": "Risk Manager",                                  "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "QRM":       {"name": "Risk Management",                               "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "OKL":       {"name": "Lease and Finance Management",                  "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "CUC":       {"name": "Revenue Accounting",                            "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "ZFA":       {"name": "Financial Analyzer",                            "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "ZPB":       {"name": "Enterprise Planning and Budgeting",             "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "BANKING":   {"name": "Banking",                                       "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "COREBANK":  {"name": "Core Banking",                                  "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "INSTITBANK":{"name": "Institutional Banking",                         "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "ISX":       {"name": "iSettlement",                                   "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "EVM":       {"name": "Value Based Management",                        "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "BLC":       {"name": "Utility Billing",                               "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "DPP":       {"name": "Oracle Price Protection",                       "domain": DOMAIN_FINANCE,       "is_obsolete": False},

    # ---- Supply Chain ----
    "INV":       {"name": "Inventory",                                     "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "PO":        {"name": "Purchasing",                                    "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "WSH":       {"name": "Shipping Execution",                            "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CST":       {"name": "Cost Management",                               "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "WMS":       {"name": "Warehouse Management",                          "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "MSC":       {"name": "Advanced Supply Chain Planning",                "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CHV":       {"name": "Supplier Scheduling",                           "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "FTE":       {"name": "Transportation Execution",                      "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "MST":       {"name": "Transportation Planning",                       "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "MSO":       {"name": "Constraint Based Optimization",                 "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "MSR":       {"name": "Inventory Optimization",                        "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "MSD":       {"name": "Demand Planning",                               "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "DDR":       {"name": "Demand Signal Repository",                      "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "INL":       {"name": "Oracle Landed Cost Management",                 "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "PON":       {"name": "Sourcing",                                      "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "POS":       {"name": "iSupplier Portal",                              "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "GML":       {"name": "Process Manufacturing Logistics",               "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CUP":       {"name": "Network Logistics – Purchasing",                "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CUI":       {"name": "Network Logistics – Inventory",                 "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CUS":       {"name": "Network Logistics",                             "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "POM":       {"name": "Exchange",                                      "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},

    # ---- Manufacturing ----
    "MFG":       {"name": "Manufacturing",                                 "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "BOM":       {"name": "Bills of Material",                             "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "ENG":       {"name": "Engineering",                                   "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "MRP":       {"name": "Master Scheduling/MRP",                         "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "CRP":       {"name": "Capacity",                                      "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "WIP":       {"name": "Work in Process",                               "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "CZ":        {"name": "Configurator",                                  "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "FLM":       {"name": "Flow Manufacturing",                            "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "PJM":       {"name": "Project Manufacturing",                         "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "WSM":       {"name": "Shop Floor Management",                         "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "WPS":       {"name": "Manufacturing Scheduling",                      "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMA":       {"name": "Process Manufacturing Systems",                 "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMI":       {"name": "Process Manufacturing Inventory",               "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMD":       {"name": "Process Manufacturing Product Development",     "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GME":       {"name": "Process Manufacturing Process Execution",       "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMP":       {"name": "Process Manufacturing Process Planning",        "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMO":       {"name": "Manufacturing Execution System for Process Manufacturing", "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GR":        {"name": "Process Manufacturing Regulatory Management",   "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "GMW":       {"name": "Process Manufacturing Portal",                  "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "EAM":       {"name": "Enterprise Asset Management",                   "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "AHL":       {"name": "Complex Maintenance Repair and Overhaul",       "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "QA":        {"name": "Quality",                                       "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "MTH":       {"name": "Oracle Manufacturing Operations Center",        "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "EGO":       {"name": "Advanced Product Catalog",                      "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
    "CSE":       {"name": "Asset Tracking",                                "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},

    # ---- Order Management ----
    "ONT":       {"name": "Order Management",                              "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "OE":        {"name": "Order Entry",                                   "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "QP":        {"name": "Advanced Pricing",                              "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "RLM":       {"name": "Release Management",                            "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "VEA":       {"name": "Automotive",                                    "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "IBE":       {"name": "iStore",                                        "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "QPR":       {"name": "Oracle Deal Management",                        "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "QOT":       {"name": "Quoting",                                       "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "ASO":       {"name": "Order Capture",                                 "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "OKT":       {"name": "Royalty Management",                            "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "PRP":       {"name": "Proposals",                                     "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},

    # ---- Human Resources ----
    "PER":       {"name": "Human Resources",                               "domain": DOMAIN_HR,            "is_obsolete": False},
    "PAY":       {"name": "Payroll",                                       "domain": DOMAIN_HR,            "is_obsolete": False},
    "FF":        {"name": "FastFormula",                                   "domain": DOMAIN_HR,            "is_obsolete": False},
    "DT":        {"name": "DateTrack",                                     "domain": DOMAIN_HR,            "is_obsolete": False},
    "SSP":       {"name": "SSP",                                           "domain": DOMAIN_HR,            "is_obsolete": False},
    "BEN":       {"name": "Advanced Benefits",                             "domain": DOMAIN_HR,            "is_obsolete": False},
    "OTA":       {"name": "Learning Management",                           "domain": DOMAIN_HR,            "is_obsolete": False},
    "HXT":       {"name": "Time and Labor",                                "domain": DOMAIN_HR,            "is_obsolete": False},
    "HXC":       {"name": "Time and Labor Engine",                         "domain": DOMAIN_HR,            "is_obsolete": False},
    "GHR":       {"name": "US Federal Human Resources",                    "domain": DOMAIN_HR,            "is_obsolete": False},
    "IRC":       {"name": "iRecruitment",                                  "domain": DOMAIN_HR,            "is_obsolete": False},
    "PSP":       {"name": "Labor Distribution",                            "domain": DOMAIN_HR,            "is_obsolete": False},

    # ---- CRM & Sales ----
    "AS":        {"name": "Sales Foundation",                              "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CN":        {"name": "Incentive Compensation",                        "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CS":        {"name": "Service",                                       "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSC":       {"name": "Customer Care",                                 "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSD":       {"name": "Depot Repair",                                  "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSF":       {"name": "Field Service",                                 "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSP":       {"name": "Spares Management",                             "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSR":       {"name": "Scheduler",                                     "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSM":       {"name": "Field Service/Palm",                            "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSL":       {"name": "Field Service/Laptop",                          "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSN":       {"name": "Call Center",                                   "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CSI":       {"name": "Install Base",                                  "domain": DOMAIN_CRM,           "is_obsolete": False},
    "OKC":       {"name": "Contracts Core",                                "domain": DOMAIN_CRM,           "is_obsolete": False},
    "OKS":       {"name": "Service Contracts",                             "domain": DOMAIN_CRM,           "is_obsolete": False},
    "OKX":       {"name": "Contracts Integration",                         "domain": DOMAIN_CRM,           "is_obsolete": False},
    "OKE":       {"name": "Project Contracts",                             "domain": DOMAIN_CRM,           "is_obsolete": False},
    "AST":       {"name": "TeleSales",                                     "domain": DOMAIN_CRM,           "is_obsolete": False},
    "ASF":       {"name": "Sales Online",                                  "domain": DOMAIN_CRM,           "is_obsolete": False},
    "ASN":       {"name": "Sales",                                         "domain": DOMAIN_CRM,           "is_obsolete": False},
    "ASL":       {"name": "Sales Offline",                                 "domain": DOMAIN_CRM,           "is_obsolete": False},
    "ASP":       {"name": "Oracle Sales for Handhelds",                    "domain": DOMAIN_CRM,           "is_obsolete": False},
    "ASG":       {"name": "CRM Gateway for Mobile Devices",                "domain": DOMAIN_CRM,           "is_obsolete": False},
    "AMS":       {"name": "Marketing",                                     "domain": DOMAIN_CRM,           "is_obsolete": False},
    "AMV":       {"name": "Marketing Encyclopedia System",                 "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IES":       {"name": "Scripting",                                     "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEM":       {"name": "Email Center",                                  "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEX":       {"name": "Collections",                                   "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEU":       {"name": "Universal Work Queue",                          "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEB":       {"name": "Interaction Blending",                          "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEO":       {"name": "Interaction Center Technology",                 "domain": DOMAIN_CRM,           "is_obsolete": False},
    "JTF":       {"name": "CRM Foundation",                                "domain": DOMAIN_CRM,           "is_obsolete": False},
    "OZF":       {"name": "Trade Management",                              "domain": DOMAIN_CRM,           "is_obsolete": False},
    "PV":        {"name": "Partner Management",                            "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IMC":       {"name": "Customers Online",                              "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CCT":       {"name": "Telephony Manager",                             "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IBU":       {"name": "iSupport",                                      "domain": DOMAIN_CRM,           "is_obsolete": False},

    # ---- Projects ----
    "PA":        {"name": "Projects",                                      "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "IPA":       {"name": "Capital Resource Logistics – Projects",         "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "PJI":       {"name": "Project Intelligence",                          "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "FPA":       {"name": "Project Portfolio Analysis",                    "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "PSB":       {"name": "Public Sector Budgeting",                       "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "GMS":       {"name": "Grants Accounting",                             "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "IGW":       {"name": "Grants Proposal",                               "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "PBR":       {"name": "Budgeting and Planning",                        "domain": DOMAIN_PROJECTS,      "is_obsolete": False},
    "ZSA":       {"name": "Sales Analyzer",                                "domain": DOMAIN_PROJECTS,      "is_obsolete": False},

    # ---- Intelligence & Analytics ----
    "BIS":       {"name": "Applications BIS",                              "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BSC":       {"name": "Balanced Scorecard",                            "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "FII":       {"name": "Financial Intelligence",                        "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "HRI":       {"name": "Human Resources Intelligence",                  "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "POA":       {"name": "Purchasing Intelligence",                       "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "OPI":       {"name": "Operations Intelligence",                       "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "ISC":       {"name": "Supply Chain Intelligence",                     "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIL":       {"name": "Sales Intelligence",                            "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIX":       {"name": "Interaction Center Intelligence",               "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIV":       {"name": "Service Intelligence",                          "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIE":       {"name": "eCommerce Intelligence",                        "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIM":       {"name": "Marketing Intelligence",                        "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "BIY":       {"name": "Systems Intelligence",                          "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "OKI":       {"name": "Contracts Intelligence",                        "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "ENI":       {"name": "Product Intelligence",                          "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "AN":        {"name": "Sales Analysis",                                "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "ODQ":       {"name": "Data Query",                                    "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "PMI":       {"name": "Process Manufacturing Intelligence",            "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "GNI":       {"name": "Genealogy Intelligence",                        "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},

    # ---- Communications & Telecom ----
    "XNM":       {"name": "Marketing for Communications",                  "domain": DOMAIN_COMMS,         "is_obsolete": True},
    "XNC":       {"name": "Sales for Communications",                      "domain": DOMAIN_COMMS,         "is_obsolete": True},
    "XNS":       {"name": "Service for Communications",                    "domain": DOMAIN_COMMS,         "is_obsolete": True},
    "XNP":       {"name": "Number Portability",                            "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "XDP":       {"name": "Provisioning",                                  "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "XNA":       {"name": "Service Assurance for Communications",          "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "XNT":       {"name": "TeleBusiness for Telecom/Utilities",            "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "BIN":       {"name": "Communications Intelligence",                   "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "CUR":       {"name": "Mass Market Receivables for Communications",    "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "XNB":       {"name": "Oracle Telecommunications Billing Integrator",  "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "XNI":       {"name": "Install Base Intelligence",                     "domain": DOMAIN_COMMS,         "is_obsolete": True},
    "MIV":       {"name": "Media Interactive",                             "domain": DOMAIN_COMMS,         "is_obsolete": False},
    "IBT":       {"name": "iAuction",                                      "domain": DOMAIN_COMMS,         "is_obsolete": False},

    # ---- Public Sector ----
    "PSA":       {"name": "Public Sector Financials",                      "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "PSR":       {"name": "Public Sector Receivables",                     "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "FV":        {"name": "Federal Financials",                            "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "IGC":       {"name": "Contract Commitment",                           "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "IGS":       {"name": "Student System",                                "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "IGF":       {"name": "Financial Aid",                                 "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "IGI":       {"name": "Public Sector Financials International",        "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "PQH":       {"name": "Public Sector HR",                              "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "PQP":       {"name": "Public Sector Payroll",                         "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "CUG":       {"name": "Citizen Interaction Center",                    "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},
    "OUC":       {"name": "University Curriculum",                         "domain": DOMAIN_PUBLIC_SECTOR, "is_obsolete": False},

    # ---- Obsolete / Other ----
    "AHM":       {"name": "Hosting Manager",                               "domain": DOMAIN_PLATFORM,      "is_obsolete": True},
    "RLA":       {"name": "Release Management Integration Kit",            "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": True},
    "VEH":       {"name": "Automotive Integration Kit",                    "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": True},
    "RHX":       {"name": "Advanced Planning Foundation",                  "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": True},
    "CSS":       {"name": "Support",                                       "domain": DOMAIN_CRM,           "is_obsolete": True},
    "ME":        {"name": "Controlled Availability Product",               "domain": DOMAIN_PLATFORM,      "is_obsolete": True},
    "BIC":       {"name": "Customer Intelligence",                         "domain": DOMAIN_ANALYTICS,     "is_obsolete": True},
    "OZP":       {"name": "Trade Planning",                                "domain": DOMAIN_CRM,           "is_obsolete": True},
    "OZS":       {"name": "iClaims",                                       "domain": DOMAIN_CRM,           "is_obsolete": True},
    "IBA":       {"name": "iMarketing",                                    "domain": DOMAIN_CRM,           "is_obsolete": True},
    "EAA":       {"name": "SEM Exchange",                                  "domain": DOMAIN_ANALYTICS,     "is_obsolete": True},
    "ABM":       {"name": "Activity Based Management",                     "domain": DOMAIN_ANALYTICS,     "is_obsolete": True},
    "CUE":       {"name": "Billing Connect",                               "domain": DOMAIN_COMMS,         "is_obsolete": True},
    "CUN":       {"name": "Network Logistics – NATS",                      "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": True},
    "DUMMY_GMO": {"name": "Obsolete Process Operations",                   "domain": DOMAIN_MANUFACTURING, "is_obsolete": True},
    "FPT":       {"name": "Banking Center",                                "domain": DOMAIN_FINANCE,       "is_obsolete": True},
    "IPD":       {"name": "Product Development",                           "domain": DOMAIN_MANUFACTURING, "is_obsolete": True},
    "OKB":       {"name": "Contracts for Subscriptions",                   "domain": DOMAIN_CRM,           "is_obsolete": True},
    "OKO":       {"name": "Contracts for Sales",                           "domain": DOMAIN_CRM,           "is_obsolete": True},
    "OKP":       {"name": "Contracts for Procurement",                     "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": True},
    "OKR":       {"name": "Contracts for Rights",                          "domain": DOMAIN_CRM,           "is_obsolete": True},
    "AMF":       {"name": "Fulfillment Services",                          "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": True},
    "IMT":       {"name": "iMeeting",                                      "domain": DOMAIN_PLATFORM,      "is_obsolete": True},
    "IBC_":      {"name": "Content Manager",                               "domain": DOMAIN_PLATFORM,      "is_obsolete": True},
    "IBW":       {"name": "Oracle Web Analytics",                          "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "RCM":       {"name": "Regulatory Capital Manager",                    "domain": DOMAIN_FINANCE,       "is_obsolete": True},
    "CLR":       {"name": "Culinary Application",                          "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CLJ":       {"name": "Japan Consulting Localizations",                "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CLL":       {"name": "LAD Consulting Localizations",                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CLE":       {"name": "EMEA Consulting Localizations",                 "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CLA":       {"name": "APAC Consulting Localizations",                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "RRC":       {"name": "Retail Core",                                   "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "RRS":       {"name": "Site Management",                               "domain": DOMAIN_ORDER_MGMT,    "is_obsolete": False},
    "PRGC":      {"name": "Progress Custom",                               "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CPGC":      {"name": "CPG – CDOA",                                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "HCP":       {"name": "Healthcare Intelligence",                       "domain": DOMAIN_ANALYTICS,     "is_obsolete": False},
    "HCA":       {"name": "Healthcare",                                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "HCC":       {"name": "iHCConnect",                                    "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "HCN":       {"name": "iHCIntegrate",                                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "HCT":       {"name": "Healthcare Terminology Server",                 "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CTB":       {"name": "Clinical Transaction Base",                     "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "CDR":       {"name": "Oracle Clinical Data Repository",               "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "ITA":       {"name": "Information Technology Audit",                  "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "IAM":       {"name": "Digital Asset Management",                      "domain": DOMAIN_PLATFORM,      "is_obsolete": False},
    "IEC":       {"name": "Advanced Outbound Telephony",                   "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IET":       {"name": "Call Center Connectors",                        "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEV":       {"name": "IVR Integrator",                                "domain": DOMAIN_CRM,           "is_obsolete": False},
    "IEP":       {"name": "Predictive",                                    "domain": DOMAIN_CRM,           "is_obsolete": False},
    "CUA":       {"name": "Capital Resource Logistics – Assets",           "domain": DOMAIN_SUPPLY_CHAIN,  "is_obsolete": False},
    "CUF":       {"name": "Capital Resource Logistics – Financials",       "domain": DOMAIN_FINANCE,       "is_obsolete": False},
    "DDD":       {"name": "CADView-3D",                                    "domain": DOMAIN_MANUFACTURING, "is_obsolete": False},
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _normalise(code: str) -> str:
    """Normalise a group code to uppercase with no surrounding whitespace."""
    return str(code or "").strip().upper()


def get_module(code: str) -> Optional[OracleModuleInfo]:
    """Return the full module info dict for *code*, or None if unknown."""
    return _CATALOG.get(_normalise(code))


def get_module_name(code: str) -> Optional[str]:
    """Return the human-readable module name, or None if unknown."""
    info = get_module(code)
    return info["name"] if info else None


def get_business_domain(code: str) -> Optional[str]:
    """Return the business domain string, or None if unknown."""
    info = get_module(code)
    return info["domain"] if info else None


def is_canonical(code: str) -> bool:
    """Return True if *code* is a known canonical Oracle module."""
    return _normalise(code) in _CATALOG


def is_obsolete(code: str) -> bool:
    """Return True if the module is flagged obsolete in the catalog."""
    info = get_module(code)
    return bool(info and info["is_obsolete"])


def format_group_label(code: str) -> str:
    """
    Return a display label for *code*.

    Examples
    --------
    ``SQLGL``  →  ``SQLGL — General Ledger``
    ``MYGRP``  →  ``MYGRP``
    """
    name = get_module_name(code)
    normalised = _normalise(code)
    return f"{normalised} — {name}" if name else normalised or str(code)


def enrich_group(code: str) -> dict:
    """
    Return a metadata dict describing *code*.

    Always returns a dict — set ``oracle_is_canonical`` to False for
    unknown codes rather than raising.

    Keys
    ----
    oracle_module_code     : str  — normalised code
    oracle_module_name     : str | None
    oracle_business_domain : str | None
    oracle_is_canonical    : bool
    oracle_is_obsolete     : bool
    """
    info = get_module(code)
    normalised = _normalise(code)
    return {
        "oracle_module_code": normalised,
        "oracle_module_name": info["name"] if info else None,
        "oracle_business_domain": info["domain"] if info else None,
        "oracle_is_canonical": info is not None,
        "oracle_is_obsolete": bool(info and info["is_obsolete"]),
    }


def all_domains() -> list[str]:
    """Return the sorted list of all distinct domain labels."""
    return sorted({v["domain"] for v in _CATALOG.values()})


def modules_in_domain(domain: str) -> list[str]:
    """Return all module codes belonging to *domain*."""
    return [k for k, v in _CATALOG.items() if v["domain"] == domain]
