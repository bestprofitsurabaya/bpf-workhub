<?php
/**
 * Konversi massal artikel classic → blok Gutenberg (tanpa mengubah konten).
 *
 * Latar (v2.46.4): artikel hasil scraper lama terbit sebagai HTML polos
 * tanpa komentar blok <!-- wp:... --> → WordPress menganggapnya SATU blok
 * Classic (tata letak "rusak" di editor sampai "Convert to blocks" manual
 * per artikel). Sejak scraper v2.46.4 artikel baru sudah Gutenberg-ready;
 * skrip ini mengonversi artikel LAMA secara massal — mekanismenya identik
 * dengan tombol "Convert to blocks": konten lewat filter
 * `rest_pre_insert_post` sehingga WP memanggil do_blocks() (reuse-existing
 * + parsing) LEBIH DULU, lalu hasilnya disimpan via wp_update_post.
 *
 * Aman-by-design:
 *  - Hanya menyentuh post yang TIDAK mengandung "<!-- wp:" (belum blok).
 *  - Tidak mengubah post_content jika hasil do_blocks() identik.
 *  - Verifikasi post-convert: seluruh HTML asli harus tetap ada (tanpa
 *    komentar blok & tanpa spasi antar-tag). Gagal verifikasi → dilewati.
 *  - wp_update_post TIDAK menyentuh tanggal/penulis/slug (field tak
 *    disertakan = tidak berubah).
 *  - Dry-run default; tambahkan --force untuk benar-benar menulis.
 *
 * Pemakaian (di server WordPress, setelah file diunggah):
 *   wp eval-file convert-classic-to-blocks.php --dry-run          # default
 *   wp eval-file convert-classic-to-blocks.php --force            # tulis
 *   wp eval-file convert-classic-to-blocks.php --force --post_type=post
 *   wp eval-file convert-classic-to-blocks.php --force --limit=50 --offset=100
 *   wp eval-file convert-classic-to-blocks.php --force --search="Bahlil"
 *   wp eval-file convert-classic-to-blocks.php --force --ids=123,456
 *
 * Opsi:
 *   --post_type=   default: post (boleh: page,post, dst.)
 *   --limit=       maksimal post diproses (default: 0 = semua)
 *   --offset=      lewati N post pertama (default: 0)
 *   --search=      hanya post yang judul/kontennya memuat teks ini
 *   --ids=         daftar ID eksplisit, dipisah koma (abaikan query lain)
 *   --force        benar-benar menyimpan perubahan (tanpa ini = dry-run)
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	echo "Skrip ini hanya bisa dijalankan via WP-CLI (wp eval-file).\n";
	exit( 1 );
}

// ── Parse argumen CLI ─────────────────────────────────────────────────────
$args = WP_CLI\Utils\get_flag_value( $assoc_args, 'ids', '' );
$post_type = WP_CLI\Utils\get_flag_value( $assoc_args, 'post_type', 'post' );
$limit = (int) WP_CLI\Utils\get_flag_value( $assoc_args, 'limit', 0 );
$offset = (int) WP_CLI\Utils\get_flag_value( $assoc_args, 'offset', 0 );
$search = (string) WP_CLI\Utils\get_flag_value( $assoc_args, 'search', '' );
$dry_run = ! array_key_exists( 'force', $assoc_args );

// ── Kandidat: hanya post BELUM blok (tanpa "<!-- wp:") ────────────────────
if ( '' !== trim( $args ) ) {
	$ids = array_filter( array_map( 'intval', explode( ',', $args ) ) );
	$posts = array();
	foreach ( $ids as $pid ) {
		$p = get_post( $pid );
		if ( $p && ! str_contains( (string) $p->post_content, '<!-- wp:' ) ) {
			$posts[] = $p;
		} elseif ( $p ) {
			WP_CLI::log( "ID {$pid}: sudah blok — dilewati." );
		} else {
			WP_CLI::warning( "ID {$pid}: tidak ditemukan." );
		}
	}
} else {
	$q = new WP_Query( array(
		'post_type'              => array_map( 'trim', explode( ',', $post_type ) ),
		'post_status'            => array( 'publish', 'future', 'draft', 'pending', 'private' ),
		's'                      => $search,
		'posts_per_page'         => ( $limit > 0 ) ? $limit : -1,
		'offset'                 => $offset,
		'fields'                 => 'all',
		'orderby'                => 'ID',
		'order'                  => 'ASC',
		'update_post_term_cache' => false,
		'update_post_meta_cache' => false,
		'no_found_rows'          => true,
	) );
	$posts = $q->posts;
}

$total = count( $posts );
WP_CLI::log( '' );
WP_CLI::log( sprintf(
	'Konversi classic → blok | %d post kandidat | MODE: %s',
	$total,
	$dry_run ? 'DRY-RUN (tanpa --force tidak ada perubahan)' : 'TULIS (--force)'
) );
WP_CLI::log( '' );

if ( ! $total ) {
	WP_CLI::success( 'Tidak ada post yang perlu dikonversi.' );
	return;
}

// ── Proses satu per satu dengan progress bar ──────────────────────────────
$progress = WP_CLI\Utils\make_progress_bar( 'Mengonversi', $total );
$converted = 0;
$skipped = 0;
$failed = 0;

foreach ( $posts as $p ) {
	$post_id = (int) $p->ID;
	$original = (string) $p->post_content;

	// Jalur REST internal: filter rest_pre_insert_post → do_blocks() di
	// dalam rest_insert_post... (jalur wp_update_post biasa TIDAK
	// memanggil do_blocks — maka filter ini dipasang manual di sini).
	$do_blocks_filter = function ( $prepared_post, $request, $supported ) use ( $post_id ) {
		if ( isset( $prepared_post->post_content ) && is_string( $prepared_post->post_content ) ) {
			$prepared_post->post_content = do_blocks( $prepared_post->post_content );
		}
		return $prepared_post;
	};
	add_filter( 'rest_pre_insert_post', $do_blocks_filter, 10, 3 );

	$rest_request = new WP_REST_Request( 'PUT', '/wp/v2/posts/' . $post_id );
	$rest_request->set_param( 'content', $original );

	$prepared = apply_filters( 'rest_pre_insert_post', null, $rest_request, true );

	remove_filter( 'rest_pre_insert_post', $do_blocks_filter, 10 );

	if ( ! is_object( $prepared ) || ! isset( $prepared->post_content ) ) {
		WP_CLI::warning( sprintf( '[%6d] gagal prepare — dilewati: %s', $post_id, wp_trim_words( get_the_title( $p ), 8 ) ) );
		++$failed;
		$progress->tick();
		continue;
	}

	$converted_html = (string) $prepared->post_content;

	// Identik → tidak ada yang perlu disimpan.
	if ( $converted_html === $original ) {
		WP_CLI::log( sprintf( '[%6d] sudah blok / tak berubah', $post_id ) );
		++$skipped;
		$progress->tick();
		continue;
	}

	// Gerbang verifikasi: seluruh HTML asli harus tetap ada setelah
	// konversi (dibandingkan tanpa komentar blok & tanpa spasi antar-tag).
	$strip_block_comments = function ( $html ) {
		$html = preg_replace( '/<!--\s*\/?wp:.*?-->/s', '', (string) $html );
		$html = preg_replace( '/>\s+</', '><', (string) $html );
		return trim( (string) $html );
	};
	if ( '' === $converted_html
		|| false === strpos( $converted_html, '<!-- wp:' )
		|| $strip_block_comments( $original ) !== $strip_block_comments( $converted_html ) ) {
		WP_CLI::warning( sprintf( '[%6d] verifikasi GAGAL — dilewati (konten tidak tersentuh)', $post_id ) );
		++$failed;
		$progress->tick();
		continue;
	}

	if ( $dry_run ) {
		$n_blocks = preg_match_all( '/<!--\s*wp:/', $converted_html );
		WP_CLI::log( sprintf( '[%6d] DRY-RUN akan dikonversi → %d blok: %s', $post_id, $n_blocks, wp_trim_words( get_the_title( $p ), 8 ) ) );
		++$converted;
		$progress->tick();
		continue;
	}

	// Tulis: hanya post_content — tanggal/penulis/slug tidak disentuh.
	$result = wp_update_post( array(
		'ID'           => $post_id,
		'post_content' => $converted_html,
	), true );

	if ( is_wp_error( $result ) ) {
		WP_CLI::warning( sprintf( '[%6d] GAGAL disimpan: %s', $post_id, $result->get_error_message() ) );
		++$failed;
	} else {
		$n_blocks = preg_match_all( '/<!--\s*wp:/', $converted_html );
		WP_CLI::log( sprintf( '[%6d] ✔ dikonversi → %d blok: %s', $post_id, $n_blocks, wp_trim_words( get_the_title( $p ), 8 ) ) );
		++$converted;
	}
	$progress->tick();
}

$progress->finish();

WP_CLI::log( '' );
WP_CLI::log( sprintf(
	'Hasil: %d dikonversi | %d dilewati (sudah blok) | %d gagal/dilewati-verifikasi%s',
	$converted,
	$skipped,
	$failed,
	$dry_run ? ' (dry-run — jalankan ulang dengan --force untuk menulis)' : ''
) );

if ( $dry_run ) {
	WP_CLI::log( 'Ini DRY-RUN — tidak ada perubahan yang ditulis.' );
}
