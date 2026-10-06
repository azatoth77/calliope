| selettore | accuratezza | diretti | passi | nessuno | falsi «nessuno» | trappole | ms mediana | ms p95 |
|---|---|---|---|---|---|---|---|---|
| gemma_json | 80 % | 62/74 | 8/8 | 4/11 | 0 | –  | 374 | 639 |
| gemma_json_banco_nuovo | 78 % | 23/26 | 0/3 | 2/3 | 1 | –  | 332 | 364 |
| gemma_json_k10 | 70 % | 56/74 | 6/8 | 3/11 | 8 | –  | 300 | 318 |
| gemma_json_trappole | 65 % | 55/74 | 5/8 | 0/11 | 0 | 26 {'imitazione': 26} | 360 | 410 |
| gemma_json_v2 | 85 % | 65/74 | 7/8 | 7/11 | 1 | –  | 363 | 410 |
| gemma_json_v2_banco_nuovo | 81 % | 23/26 | 1/3 | 2/3 | 1 | –  | 351 | 394 |
| gemma_json_v2_trappole | 75 % | 65/74 | 5/8 | 0/11 | 0 | 18 {'imitazione': 18} | 386 | 419 |
| gemma_tool | 81 % | 62/74 | 7/8 | 6/11 | 4 | –  | 388 | 443 |
| gemma_tool_v2 | 84 % | 67/74 | 5/8 | 6/11 | 3 | –  | 342 | 459 |
| gemma_tool_v2_banco_nuovo | 78 % | 23/26 | 0/3 | 2/3 | 2 | –  | 334 | 446 |
| laya_english_etichette | 13 % | 9/74 | 0/8 | 3/11 | 17 | –  | 845 | 1056 |
| laya_multilingual_codici | 26 % | 23/74 | 1/8 | 0/11 | 6 | –  | 295 | 376 |
| laya_multilingual_etichette | 30 % | 27/74 | 1/8 | 0/11 | 1 | –  | 241 | 333 |
| laya_multilingual_etichette_banco_nuovo | 47 % | 15/26 | 0/3 | 0/3 | 2 | –  | 239 | 326 |
| laya_multilingual_etichette_k8 | 32 % | 25/74 | 2/8 | 3/11 | 14 | –  | 152 | 196 |
| laya_typed-decisions_etichette | 18 % | 17/74 | 0/8 | 0/11 | 1 | –  | 846 | 1012 |
| lessicale | 54 % | 46/74 | 4/8 | 0/11 | 0 | –  | 172 | 323 |
| lessicale_banco_nuovo | 62 % | 20/26 | 0/3 | 0/3 | 0 | –  | 76 | 124 |
| rizzo_1.7b_q8_cpu8 | 23 % | 19/74 | 0/8 | 2/11 | 14 | –  | 4222 | 4921 |
| rizzo_1.7b_q8_gpu | 22 % | 18/74 | 0/8 | 2/11 | 15 | –  | 74 | 84 |
| rizzo_4b_q4_cpu8 | 46 % | 34/74 | 4/8 | 5/11 | 21 | –  | 7062 | 8235 |
| rizzo_4b_q8_gpu | 55 % | 40/74 | 4/8 | 7/11 | 13 | –  | 147 | 168 |
| rizzo_4b_q8_gpu_banco_nuovo | 44 % | 12/26 | 0/3 | 2/3 | 7 | –  | 148 | 165 |
| rizzo_4b_q8_gpu_en | 54 % | 43/74 | 3/8 | 4/11 | 8 | –  | 146 | 165 |
| rizzo_4b_q8_gpu_en_banco_nuovo | 47 % | 14/26 | 0/3 | 1/3 | 2 | –  | 142 | 163 |
| rizzo_4b_q8_gpu_en_k8 | 46 % | 38/74 | 2/8 | 3/11 | 13 | –  | 97 | 107 |
| rizzo_4b_q8_gpu_k8 | 49 % | 38/74 | 4/8 | 4/11 | 19 | –  | 98 | 107 |
| rizzo_4b_q8_gpu_trappole | 51 % | 38/74 | 4/8 | 5/11 | 10 | 18 {'imitazione': 18} | 162 | 184 |

| selettore | barra | blocco note | edge | esplora | impostazioni | vscode |
|---|---|---|---|---|---|---|
| gemma_json | 10/12 | 7/8 | 8/8 | 16/25 | 27/31 | 6/9 |
| gemma_json_banco_nuovo | 2/4 | 3/3 | 2/3 | 6/8 | 10/11 | 2/3 |
| gemma_json_k10 | 9/12 | 4/8 | 7/8 | 17/25 | 23/31 | 5/9 |
| gemma_json_trappole | 4/12 | 7/8 | 6/8 | 14/25 | 23/31 | 6/9 |
| gemma_json_v2 | 11/12 | 8/8 | 8/8 | 18/25 | 27/31 | 7/9 |
| gemma_json_v2_banco_nuovo | 3/4 | 3/3 | 2/3 | 6/8 | 10/11 | 2/3 |
| gemma_json_v2_trappole | 10/12 | 7/8 | 6/8 | 18/25 | 23/31 | 6/9 |
| gemma_tool | 9/12 | 8/8 | 8/8 | 20/25 | 25/31 | 5/9 |
| gemma_tool_v2 | 11/12 | 8/8 | 7/8 | 22/25 | 25/31 | 5/9 |
| gemma_tool_v2_banco_nuovo | 2/4 | 3/3 | 2/3 | 6/8 | 10/11 | 2/3 |
| laya_english_etichette | 4/12 | 2/8 | 0/8 | 2/25 | 4/31 | 0/9 |
| laya_multilingual_codici | 5/12 | 0/8 | 2/8 | 5/25 | 12/31 | 0/9 |
| laya_multilingual_etichette | 5/12 | 2/8 | 0/8 | 6/25 | 13/31 | 2/9 |
| laya_multilingual_etichette_banco_nuovo | 2/4 | 2/3 | 1/3 | 3/8 | 5/11 | 2/3 |
| laya_multilingual_etichette_k8 | 5/12 | 0/8 | 1/8 | 9/25 | 12/31 | 3/9 |
| laya_typed-decisions_etichette | 4/12 | 1/8 | 2/8 | 0/25 | 7/31 | 3/9 |
| lessicale | 9/12 | 4/8 | 5/8 | 15/25 | 16/31 | 1/9 |
| lessicale_banco_nuovo | 2/4 | 3/3 | 2/3 | 6/8 | 7/11 | 0/3 |
| rizzo_1.7b_q8_cpu8 | 1/12 | 3/8 | 4/8 | 1/25 | 11/31 | 1/9 |
| rizzo_1.7b_q8_gpu | 1/12 | 3/8 | 3/8 | 1/25 | 11/31 | 1/9 |
| rizzo_4b_q4_cpu8 | 3/12 | 3/8 | 6/8 | 7/25 | 19/31 | 5/9 |
| rizzo_4b_q8_gpu | 5/12 | 3/8 | 6/8 | 8/25 | 24/31 | 5/9 |
| rizzo_4b_q8_gpu_banco_nuovo | 1/4 | 1/3 | 1/3 | 1/8 | 9/11 | 1/3 |
| rizzo_4b_q8_gpu_en | 6/12 | 3/8 | 7/8 | 10/25 | 18/31 | 6/9 |
| rizzo_4b_q8_gpu_en_banco_nuovo | 3/4 | 1/3 | 2/3 | 2/8 | 6/11 | 1/3 |
| rizzo_4b_q8_gpu_en_k8 | 6/12 | 2/8 | 6/8 | 9/25 | 15/31 | 5/9 |
| rizzo_4b_q8_gpu_k8 | 6/12 | 2/8 | 5/8 | 10/25 | 18/31 | 5/9 |
| rizzo_4b_q8_gpu_trappole | 4/12 | 3/8 | 5/8 | 8/25 | 22/31 | 5/9 |

**gemma_json**: AUROC 0.86
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 80 % | 19 (19) | 0 |
| 0.5 | 94 % | 84 % | 14 (14) | 6 |
| 0.6 | 83 % | 87 % | 10 (10) | 16 |
| 0.7 | 75 % | 91 % | 6 (6) | 23 |
| 0.8 | 73 % | 91 % | 6 (6) | 25 |
| 0.9 | 61 % | 95 % | 3 (3) | 36 |
| 0.95 | 44 % | 95 % | 2 (2) | 52 |

**gemma_json_banco_nuovo**: AUROC 0.75
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 78 % | 7 (6) | 0 |
| 0.5 | 97 % | 77 % | 7 (6) | 1 |
| 0.6 | 75 % | 83 % | 4 (4) | 8 |
| 0.7 | 75 % | 83 % | 4 (4) | 8 |
| 0.8 | 59 % | 95 % | 1 (1) | 13 |
| 0.9 | 56 % | 94 % | 1 (1) | 14 |
| 0.95 | 41 % | 92 % | 1 (1) | 19 |

**gemma_json_k10**: AUROC 0.78
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 70 % | 28 (20) | 0 |
| 0.5 | 94 % | 71 % | 25 (17) | 6 |
| 0.6 | 90 % | 71 % | 24 (16) | 9 |
| 0.7 | 82 % | 74 % | 20 (13) | 17 |
| 0.8 | 74 % | 75 % | 17 (11) | 24 |
| 0.9 | 56 % | 85 % | 8 (3) | 41 |
| 0.95 | 41 % | 97 % | 1 (0) | 55 |

**gemma_json_trappole**: AUROC 0.71
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 65 % | 33 (33) | 0 |
| 0.5 | 94 % | 66 % | 30 (30) | 6 |
| 0.6 | 89 % | 67 % | 27 (27) | 10 |
| 0.7 | 78 % | 70 % | 22 (22) | 20 |
| 0.8 | 70 % | 74 % | 17 (17) | 28 |
| 0.9 | 54 % | 76 % | 12 (12) | 43 |
| 0.95 | 37 % | 79 % | 7 (7) | 59 |

**gemma_json_v2**: AUROC 0.91
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 85 % | 14 (13) | 0 |
| 0.5 | 96 % | 87 % | 12 (11) | 4 |
| 0.6 | 86 % | 91 % | 7 (6) | 13 |
| 0.7 | 84 % | 92 % | 6 (5) | 15 |
| 0.8 | 77 % | 96 % | 3 (2) | 21 |
| 0.9 | 66 % | 98 % | 1 (1) | 32 |
| 0.95 | 52 % | 100 % | 0 (0) | 45 |

**gemma_json_v2_banco_nuovo**: AUROC 0.86
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 81 % | 6 (5) | 0 |
| 0.5 | 91 % | 83 % | 5 (4) | 3 |
| 0.6 | 88 % | 82 % | 5 (4) | 4 |
| 0.7 | 81 % | 88 % | 3 (3) | 6 |
| 0.8 | 66 % | 95 % | 1 (1) | 11 |
| 0.9 | 59 % | 100 % | 0 (0) | 13 |
| 0.95 | 50 % | 100 % | 0 (0) | 16 |

**gemma_json_v2_trappole**: AUROC 0.83
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 75 % | 23 (23) | 0 |
| 0.5 | 96 % | 76 % | 21 (21) | 4 |
| 0.6 | 91 % | 76 % | 20 (20) | 8 |
| 0.7 | 84 % | 79 % | 16 (16) | 15 |
| 0.8 | 69 % | 86 % | 9 (9) | 29 |
| 0.9 | 56 % | 96 % | 2 (2) | 41 |
| 0.95 | 45 % | 98 % | 1 (1) | 51 |

**laya_english_etichette**: AUROC 0.50
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 13 % | 81 (64) | 0 |
| 0.5 | 12 % | 18 % | 9 (7) | 82 |
| 0.6 | 6 % | 33 % | 4 (2) | 87 |
| 0.7 | 3 % | 33 % | 2 (0) | 90 |
| 0.8 | 1 % | 100 % | 0 (0) | 92 |
| 0.9 | 1 % | 100 % | 0 (0) | 92 |
| 0.95 | 0 % | – | 0 (0) | 93 |

**laya_multilingual_codici**: AUROC 0.64
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 26 % | 69 (63) | 0 |
| 0.5 | 12 % | 45 % | 6 (6) | 82 |
| 0.6 | 9 % | 50 % | 4 (4) | 85 |
| 0.7 | 5 % | 60 % | 2 (2) | 88 |
| 0.8 | 3 % | 67 % | 1 (1) | 90 |
| 0.9 | 3 % | 67 % | 1 (1) | 90 |
| 0.95 | 1 % | 100 % | 0 (0) | 92 |

**laya_multilingual_etichette**: AUROC 0.71
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 30 % | 65 (64) | 0 |
| 0.5 | 32 % | 37 % | 19 (19) | 63 |
| 0.6 | 19 % | 61 % | 7 (7) | 75 |
| 0.7 | 14 % | 62 % | 5 (5) | 80 |
| 0.8 | 9 % | 75 % | 2 (2) | 85 |
| 0.9 | 5 % | 80 % | 1 (1) | 88 |
| 0.95 | 1 % | 100 % | 0 (0) | 92 |

**laya_multilingual_etichette_banco_nuovo**: AUROC 0.77
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 47 % | 17 (15) | 0 |
| 0.5 | 41 % | 69 % | 4 (3) | 19 |
| 0.6 | 34 % | 64 % | 4 (3) | 21 |
| 0.7 | 28 % | 67 % | 3 (2) | 23 |
| 0.8 | 22 % | 86 % | 1 (1) | 25 |
| 0.9 | 12 % | 75 % | 1 (1) | 28 |
| 0.95 | 6 % | 50 % | 1 (1) | 30 |

**laya_multilingual_etichette_k8**: AUROC 0.71
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 32 % | 63 (49) | 0 |
| 0.5 | 53 % | 41 % | 29 (23) | 44 |
| 0.6 | 37 % | 53 % | 16 (14) | 59 |
| 0.7 | 27 % | 64 % | 9 (9) | 68 |
| 0.8 | 17 % | 75 % | 4 (4) | 77 |
| 0.9 | 12 % | 73 % | 3 (3) | 82 |
| 0.95 | 8 % | 71 % | 2 (2) | 86 |

**laya_typed-decisions_etichette**: AUROC 0.57
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 18 % | 76 (75) | 0 |
| 0.5 | 3 % | 33 % | 2 (2) | 90 |
| 0.6 | 0 % | – | 0 (0) | 93 |
| 0.7 | 0 % | – | 0 (0) | 93 |
| 0.8 | 0 % | – | 0 (0) | 93 |
| 0.9 | 0 % | – | 0 (0) | 93 |
| 0.95 | 0 % | – | 0 (0) | 93 |

**lessicale**: AUROC 0.73
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 54 % | 43 (43) | 0 |
| 1.0 | 72 % | 67 % | 22 (22) | 26 |
| 1.1 | 35 % | 70 % | 10 (10) | 60 |
| 1.2 | 23 % | 71 % | 6 (6) | 72 |
| 1.25 | 18 % | 76 % | 4 (4) | 76 |
| 1.3 | 6 % | 100 % | 0 (0) | 87 |

**lessicale_banco_nuovo**: AUROC 0.82
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 62 % | 12 (12) | 0 |
| 1.0 | 84 % | 74 % | 7 (7) | 5 |
| 1.1 | 38 % | 83 % | 2 (2) | 20 |
| 1.2 | 28 % | 89 % | 1 (1) | 23 |
| 1.25 | 22 % | 86 % | 1 (1) | 25 |
| 1.3 | 9 % | 67 % | 1 (1) | 29 |

**rizzo_1.7b_q8_cpu8**: AUROC 0.64
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 23 % | 72 (58) | 0 |
| 0.5 | 58 % | 30 % | 38 (34) | 39 |
| 0.6 | 43 % | 30 % | 28 (25) | 53 |
| 0.7 | 27 % | 28 % | 18 (16) | 68 |
| 0.8 | 13 % | 33 % | 8 (8) | 81 |
| 0.9 | 6 % | 50 % | 3 (3) | 87 |
| 0.95 | 3 % | 67 % | 1 (1) | 90 |

**rizzo_1.7b_q8_gpu**: AUROC 0.68
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 22 % | 73 (58) | 0 |
| 0.5 | 63 % | 29 % | 42 (36) | 34 |
| 0.6 | 39 % | 31 % | 25 (22) | 57 |
| 0.7 | 27 % | 28 % | 18 (16) | 68 |
| 0.8 | 12 % | 36 % | 7 (7) | 82 |
| 0.9 | 5 % | 60 % | 2 (2) | 88 |
| 0.95 | 3 % | 67 % | 1 (1) | 90 |

**rizzo_4b_q4_cpu8**: AUROC 0.78
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 46 % | 50 (29) | 0 |
| 0.5 | 71 % | 55 % | 30 (13) | 27 |
| 0.6 | 51 % | 66 % | 16 (6) | 46 |
| 0.7 | 42 % | 72 % | 11 (3) | 54 |
| 0.8 | 33 % | 81 % | 6 (2) | 62 |
| 0.9 | 19 % | 78 % | 4 (1) | 75 |
| 0.95 | 10 % | 89 % | 1 (0) | 84 |

**rizzo_4b_q8_gpu**: AUROC 0.69
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 55 % | 42 (29) | 0 |
| 0.5 | 81 % | 59 % | 31 (19) | 18 |
| 0.6 | 65 % | 62 % | 23 (12) | 33 |
| 0.7 | 53 % | 69 % | 15 (5) | 44 |
| 0.8 | 41 % | 71 % | 11 (2) | 55 |
| 0.9 | 25 % | 78 % | 5 (1) | 70 |
| 0.95 | 16 % | 87 % | 2 (1) | 78 |

**rizzo_4b_q8_gpu_banco_nuovo**: AUROC 0.71
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 44 % | 18 (11) | 0 |
| 0.5 | 78 % | 52 % | 12 (7) | 7 |
| 0.6 | 50 % | 50 % | 8 (3) | 16 |
| 0.7 | 38 % | 67 % | 4 (0) | 20 |
| 0.8 | 28 % | 78 % | 2 (0) | 23 |
| 0.9 | 16 % | 80 % | 1 (0) | 27 |
| 0.95 | 6 % | 100 % | 0 (0) | 30 |

**rizzo_4b_q8_gpu_en**: AUROC 0.81
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 54 % | 43 (35) | 0 |
| 0.5 | 81 % | 61 % | 29 (21) | 18 |
| 0.6 | 67 % | 68 % | 20 (12) | 31 |
| 0.7 | 48 % | 80 % | 9 (7) | 48 |
| 0.8 | 37 % | 85 % | 5 (5) | 59 |
| 0.9 | 20 % | 89 % | 2 (2) | 74 |
| 0.95 | 13 % | 100 % | 0 (0) | 81 |

**rizzo_4b_q8_gpu_en_banco_nuovo**: AUROC 0.78
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 47 % | 17 (15) | 0 |
| 0.5 | 72 % | 57 % | 10 (8) | 9 |
| 0.6 | 34 % | 73 % | 3 (3) | 21 |
| 0.7 | 25 % | 88 % | 1 (1) | 24 |
| 0.8 | 22 % | 86 % | 1 (1) | 25 |
| 0.9 | 12 % | 100 % | 0 (0) | 28 |
| 0.95 | 9 % | 100 % | 0 (0) | 29 |

**rizzo_4b_q8_gpu_en_k8**: AUROC 0.81
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 46 % | 50 (37) | 0 |
| 0.5 | 80 % | 54 % | 34 (24) | 19 |
| 0.6 | 59 % | 64 % | 20 (14) | 38 |
| 0.7 | 46 % | 72 % | 12 (11) | 50 |
| 0.8 | 30 % | 86 % | 4 (4) | 65 |
| 0.9 | 19 % | 94 % | 1 (1) | 75 |
| 0.95 | 9 % | 100 % | 0 (0) | 85 |

**rizzo_4b_q8_gpu_k8**: AUROC 0.69
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 49 % | 47 (28) | 0 |
| 0.5 | 72 % | 55 % | 30 (16) | 26 |
| 0.6 | 55 % | 57 % | 22 (8) | 42 |
| 0.7 | 43 % | 65 % | 14 (5) | 53 |
| 0.8 | 32 % | 70 % | 9 (2) | 63 |
| 0.9 | 14 % | 69 % | 4 (2) | 80 |
| 0.95 | 8 % | 71 % | 2 (1) | 86 |

**rizzo_4b_q8_gpu_trappole**: AUROC 0.63
| soglia | eseguite da sole | giuste tra quelle | errori automatici (di cui azioni) | a conferma |
|---|---|---|---|---|
| 0.0 | 100 % | 51 % | 46 (36) | 0 |
| 0.5 | 74 % | 54 % | 32 (24) | 24 |
| 0.6 | 55 % | 63 % | 19 (14) | 42 |
| 0.7 | 40 % | 65 % | 13 (9) | 56 |
| 0.8 | 24 % | 68 % | 7 (5) | 71 |
| 0.9 | 16 % | 73 % | 4 (2) | 78 |
| 0.95 | 5 % | 80 % | 1 (0) | 88 |

