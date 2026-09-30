<?php
/**
 * Isi meta Rank Math (focus keyword, meta description, SEO title) secara
 * massal dari judul post — jalur WP-CLI.
 *
 * Latar (v2.46.4/v2.46.5): WorkHub mengirim meta rank_math_* via REST API,
 * tetapi beberapa situs BPF memfilter meta REST (hardening keamanan) sehingga
 * field itu diabaikan server. Skrip ini menulis meta yang sama langsung di
 * server WordPress (update_post_meta) — tidak lewat REST — sehingga selalu
 * berhasil tanpa menyentuh konten/tanggal/penulis post.
 *
 * Logika (identik dengan scraper v2.46.5):
 *  - focus keyword : ≤4 kata pertama judul yang bermakna (>3 huruf,
 *                    bukan stopword: dan/di/ke/dari/yang/untuk/dengan/ini/itu/…)
 *  - description   : render template {judul}/{kategori}/{sumber}/{tanggal}
 *                    lalu dipotong ≤160 karakter di batas kata
 *  - title         : render template yang sama, dipotong ≤60 karakter
 *  - placeholder {excerpt}: potongan isi post (fallback description)
 *
 * Default hanya menyentuh post yang meta-nya MASIH KOSONG — aman dijalankan
 * berulang (idempoten); post yang sudah diisi (manual/scraper) tidak diubah.
 *
 * Pemakaian (di server WordPress, setelah file diunggah):
 *   wp eval-file fill-rank-math-meta.php --dry-run            # default
 *   wp eval-file fill-rank-math-meta.php --force              # tulis
 *   wp eval-file fill-rank-math-meta.php --force --post_ids=45385,45387
 *   wp eval-file fill-rank-math-meta.php --force --limit=100
 *   wp eval-file fill-rank-math-meta.php --force \
 *       --desc_tpl="Update {judul} — analisis pasar dari {sumber}." \
 *       --title_tpl="{judul} | {kategori}"
 *   wp eval-file fill-rank-math-meta.php --force --overwrite  # timpa meta lama
 *
 * Opsi:
 *   --post_type=  default: post
 *   --post_ids=   daftar ID eksplisit, dipisah koma (abaikan query lain)
 *   --limit=      maksimal post diproses (default: 0 = semua)
 *   --offset=     lewati N post pertama (default: 0)
 *   --desc_tpl=   template description (default: "{judul}. {excerpt}")
 *   --title_tpl=  template title (default: "{judul}")
 *   --overwrite   timpa meta yang sudah terisi (default: hanya isi kosong)
 *   --force       benar-benar menulis (tanpa ini = dry-run)
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	echo "Skrip ini hanya bisa dijalankan via WP-CLI (wp eval-file).\n";
	exit( 1 );
}

$post_type = WP_CLI\Utils\get_flag_value( $assoc_args, 'post_type', 'post' );
$post_ids_arg = (string) WP_CLI\Utils\get_flag_value( $assoc_args, 'post_ids', '' );
$limit = (int) WP_CLI\Utils\get_flag_value( $assoc_args, 'limit', 0 );
$offset = (int) WP_CLI\Utils\get_flag_value( $assoc_args, 'offset', 0 );
$desc_tpl = (string) WP_CLI\Utils\get_flag_value( $assoc_args, 'desc_tpl', '{judul}. {excerpt}' );
$title_tpl = (string) WP_CLI\Utils\get_flag_value( $assoc_args, 'title_tpl', '{judul}' );
$overwrite = array_key_exists( 'overwrite', $assoc_args );
$dry_run = ! array_key_exists( 'force', $assoc_args );

// ── Helper (logika sama dengan routes.py versi Python) ────────────────────
$stopwords = array( 'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan',
	'ini', 'itu', 'atau', 'dalam', 'pada', 'the' );

$focus_keyword = function ( $title, $max_words = 4 ) use ( $stopwords ) {
	$words = preg_split( '/\s+/', trim( (string) $title ) ) ?: array();
	$picked = array();
	foreach ( $words as $w ) {
		$w = trim( $w, " \t\n\r.,:;!?()\"“”‘’" );
		if ( '' === $w || mb_strlen( $w ) <= 3 || in_array( mb_strtolower( $w ), $stopwords, true ) ) {
			continue;
		}
		$picked[] = $w;
		if ( count( $picked ) >= $max_words ) {
			break;
		}
	}
	return implode( ' ', $picked );
};

$render_tpl = function ( $tpl, $title, $category, $source, $date, $excerpt ) {
	$out = str_replace(
		array( '{judul}', '{kategori}', '{sumber}', '{tanggal}', '{excerpt}' ),
		array( (string) $title, (string) $category, (string) $source, (string) $date, (string) $excerpt ),
		(string) $tpl
	);
	return trim( preg_replace( '/\s+/', ' ', $out ) );
};

$trim_words_safe = function ( $text, $limit ) {
	$text = trim( (string) $text );
	if ( mb_strlen( $text ) <= $limit ) {
		return $text;
	}
	$cut = mb_substr( $text, 0, $limit );
	$pos = mb_strrpos( $cut, ' ' );
	return ( false !== $pos ) ? mb_substr( $cut, 0, $pos ) : $cut;
};

// ── Kandidat post ─────────────────────────────────────────────────────────
if ( '' !== trim( $post_ids_arg ) ) {
	$ids = array_filter( array_map( 'intval', explode( ',', $post_ids_arg ) ) );
	$posts = array();
	foreach ( $ids as $pid ) {
		$p = get_post( $pid );
		if ( $p ) {
			$posts[] = $p;
		} else {
			WP_CLI::warning( "ID {$pid}: tidak ditemukan." );
		}
	}
} else {
	$q = new WP_Query( array(
		'post_type'              => array_map( 'trim', explode( ',', $post_type ) ),
		'post_status'            => array( 'publish', 'future', 'draft', 'pending', 'private' ),
		'posts_per_page'         => ( $limit > 0 ) ? $limit : -1,
		'offset'                 => $offset,
		'orderby'                => 'ID',
		'order'                  => 'DESC',
		'update_post_term_cache' => false,
		'no_found_rows'          => true,
	) );
	$posts = $q->posts;
}

$total = count( $posts );
WP_CLI::log( '' );
WP_CLI::log( sprintf(
	'Isi meta Rank Math | %d post kandidat | MODE: %s%s',
	$total,
	$dry_run ? 'DRY-RUN' : 'TULIS (--force)',
	$overwrite ? ' | overwrite meta lama' : ' | hanya meta kosong'
) );
WP_CLI::log( '' );

if ( ! $total ) {
	WP_CLI::success( 'Tidak ada post yang perlu diproses.' );
	return;
}

$progress = WP_CLI\Utils\make_progress_bar( 'Memproses', $total );
$filled = 0;
$skipped = 0;

foreach ( $posts as $p ) {
	$post_id = (int) $p->ID;

	$kw_lama  = get_post_meta( $post_id, 'rank_math_focus_keyword', true );
	$desc_lama = get_post_meta( $post_id, 'rank_math_description', true );
	$title_lama = get_post_meta( $post_id, 'rank_math_title', true );

	if ( ! $overwrite && ( '' !== (string) $kw_lama || '' !== (string) $desc_lama || '' !== (string) $title_lama ) ) {
		++$skipped;
		$progress->tick();
		continue;
	}

	$title = get_the_title( $p );
	$category = '';
	$cats = get_the_category( $post_id );
	if ( ! empty( $cats ) && ! is_wp_error( $cats ) ) {
		$category = $cats[0]->name;
	}
	$excerpt = wp_trim_words( wp_strip_all_tags( (string) $p->post_content ), 25, '…' );

	$kw_baru = $focus_keyword( $title );
	$desc_baru = $trim_words_safe( $render_tpl( $desc_tpl, $title, $category, '', get_the_date( 'Y-m-d', $post_id ), $excerpt ), 160 );
	$title_baru = $trim_words_safe( $render_tpl( $title_tpl, $title, $category, '', get_the_date( 'Y-m-d', $post_id ), $excerpt ), 60 );

	if ( '' === $kw_baru && '' === $desc_baru ) {
		++$skipped;
		$progress->tick();
		continue;
	}

	WP_CLI::log( sprintf( '[%6d] kw="%s" | desc="%s…" | title="%s…"',
		$post_id, $kw_baru, mb_substr( $desc_baru, 0, 40 ), mb_substr( $title_baru, 0, 40 ) ) );

	if ( ! $dry_run ) {
		if ( '' !== $kw_baru ) {
			update_post_meta( $post_id, 'rank_math_focus_keyword', $kw_baru );
		}
		if ( '' !== $desc_baru ) {
			update_post_meta( $post_id, 'rank_math_description', $desc_baru );
		}
		if ( '' !== $title_baru ) {
			update_post_meta( $post_id, 'rank_math_title', $title_baru );
		}
		// Rank Math mengatur meta sendiri per-post di tabel postmeta; nilai
		// baru langsung terbaca tanpa flush apa pun.
	}
	++$filled;
	$progress->tick();
}

$progress->finish();

WP_CLI::log( '' );
WP_CLI::log( sprintf(
	'Hasil: %d diisi | %d dilewati (meta sudah ada%s)%s',
	$filled,
	$skipped,
	$overwrite ? '' : ' — pakai --overwrite untuk menimpa',
	$dry_run ? ' | DRY-RUN — jalankan ulang dengan --force untuk menulis' : ''
) );
