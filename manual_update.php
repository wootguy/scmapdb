<?php
	// Turn off output buffering
	ini_set('output_buffering', 'off');
	// Turn off PHP output compression
	ini_set('zlib.output_compression', false);
			 
	//Flush (send) the output buffer and turn off output buffering
	//ob_end_flush();
	while (@ob_end_flush());
			 
	// Implicitly flush the buffer(s)
	ini_set('implicit_flush', true);
	ob_implicit_flush(true);
	 
	//prevent apache from buffering it for deflate/gzip
	header("Content-type: text/plain");
	header('Cache-Control: no-cache'); // recommended to prevent caching of event data.
	 
	for($i = 0; $i < 8192; $i++)
	{
		echo ' ';
	}
			 
	ob_flush();
	flush();
	 
	/// Now start the program output
	 
	echo "Starting script...\n\n";

	$cmd = "sh /media/sda1/html/scmapdb/cmd.sh 2>&1";
	//while (@ ob_end_flush()); // end all output buffers if any

	$proc = popen($cmd, 'r');
	@ flush();
	while (!feof($proc))
	{
		echo fread($proc, 4);
		@ flush();
	}
	fclose($proc);
	 
	ob_flush();
	flush();
?>